# Multimodal Vision-Language Emotion Understanding

Temporal valence/arousal regression on the **AFEW-VA** video dataset using CLIP image encoders, LoRA adapters, a lightweight temporal aggregation head, and a two-stage training loop: contrastive pretraining followed by CCC-supervised regression fine-tuning.

A second pipeline (Pipeline B) pre-extracts and caches CLIP features to enable fast iteration on memory-constrained GPUs (~20 GB).

---

## Results

| Pipeline | CCC (Valence) | CCC (Arousal) | CCC (Mean) |
|---|---|---|---|
| Pipeline A (CLIP + LoRA) | 0.447 | 0.412 | **0.430** |
| Pipeline B (Cached features) | 0.389 | 0.371 | 0.380 |

**Configuration:** NVIDIA A100 (40GB) • Mixed precision (FP16) • ~3.5 hours training

**Key findings:**
- LoRA fine-tuning of CLIP provides +5% CCC over cached features alone
- Two-stage contrastive pretraining stabilizes regression convergence
- Mean CCC of 0.43 competitive with vision-only AFEW-VA benchmarks (0.35–0.55 range)

### Visualizations

<table>
<tr>
<td width="50%">

**Valence-Arousal Space**

![2D Valence-Arousal Space](outputs/visualizations/2d_valence_arousal_space.png)

*Predicted vs. ground-truth valence/arousal distributions showing model calibration.*

</td>
<td width="50%">

**Temporal Analysis**

![Temporal Analysis](outputs/visualizations/temporal_analysis.png)

*Frame-level predictions over time demonstrating temporal consistency.*

</td>
</tr>
<tr>
<td width="50%">

**UMAP Embedding Space**

![UMAP Visualization](outputs/visualizations/umap_primary_visualization.png)

*Learned emotion embeddings in 2D space after contrastive pretraining.*

</td>
<td width="50%">

**PCA Analysis**

![PCA Validation](outputs/visualizations/pca_validation_analysis.png)

*Principal component analysis of validation set embeddings.*

</td>
</tr>
</table>

---

## Architecture

```
Video frames
    │
    ▼
CLIP ViT-B/32 (frozen)
    │  + LoRA on Q, V projections of last transformer block
    │    (rank=8, alpha=16 — ~200K trainable params in backbone)
    ▼
FrameProjector  [512 → 512 → 128, L2-norm]
    │
    ├──► TemporalHead  [mean-pool → linear → L2-norm]  → clip embedding g ∈ ℝ¹²⁸
    │
    └──► RegressionHead  [128 → 64 → 2]  → (valence, arousal) per frame
```

### Two-stage Training

**Stage 1 — Contrastive Pretraining**

Trains `FrameProjector`, `TemporalHead`, and LoRA matrices using three losses:

| Loss | Purpose |
|---|---|
| Local-Local (InfoNCE) | Adjacent frames with similar VA values attract; dissimilar frames repel. Negatives include a 4096-slot MoCo-style memory queue. |
| Global-Local (InfoNCE) | Each clip embedding `g` pulls toward all its own frame embeddings and pushes away frames from other clips. |
| Smoothness | L2 penalty on consecutive frame embedding differences for temporally coherent trajectories. |

**Stage 2 — Regression Fine-tuning**

Trains `TemporalHead` + `RegressionHead` + LoRA with a combined MSE + CCC loss.

> **CCC (Concordance Correlation Coefficient)** is the standard metric for affective computing — it jointly penalises scale, location, and correlation errors, making it more informative than MSE for continuous emotion prediction.

---

## Repository Layout

```
├── pipeline_a/               # Main pipeline (CLIP + LoRA, end-to-end)
│   ├── model.py              # TemporalEmotionModel with LoRA injection
│   ├── losses.py             # InfoNCE, CCC, smoothness losses
│   ├── dataset.py            # AFEW-VA loader with temporal sampling
│   ├── train_pretrain.py     # Stage 1 training loop
│   ├── train_finetune.py     # Stage 2 training loop
│   ├── evaluate.py           # Evaluation + visualisation
│   ├── config.py             # All hyperparameters
│   └── main.py               # CLI entry point
│
├── pipeline_b/               # Cached-feature pipeline (~20 GB GPUs)
│   ├── 1_extract_features.py # Run once: extract + cache CLIP features
│   ├── 2_dataset.py
│   ├── 3_model.py            # Temporal transformer head only
│   ├── 4_loss.py
│   └── 5_train.py
│
├── outputs/visualizations/   # UMAP, PCA, valence-arousal space plots
├── results/                  # Training curves, evaluation outputs
└── legacy/                   # Previous experimental implementations
```

---

## Dataset Preparation (AFEW-VA)

```
dataset/
  001/
    00000.png
    00001.png
    ...
    001.json        # frame-level valence/arousal annotations
  002/
    ...
```

Pass the root path with `--dataset` or edit `config.py`.

---

## Pipeline A — Full CLIP + LoRA Training

```bash
cd pipeline_a
pip install -r requirements.txt

# Stage 1: contrastive pretraining
python main.py --stage pretrain --dataset /path/to/AFEW-VA

# Stage 2: regression fine-tuning
python main.py --stage finetune --dataset /path/to/AFEW-VA \
    --checkpoint checkpoints/pretrain_best.pth

# Both stages in one go
python main.py --stage all --dataset /path/to/AFEW-VA

# Evaluation only
python main.py --stage evaluate --dataset /path/to/AFEW-VA \
    --checkpoint checkpoints/finetune_best_best.pth
```

Useful overrides: `--batch_size`, `--num_frames`, `--epochs_pretrain`, `--epochs_finetune`, `--seed`.

---

## Pipeline B — Cached-Feature Temporal Head

Faster when GPU memory or time is limited. Trains only a temporal transformer on pre-extracted CLIP features.

```bash
cd pipeline_b

# Step 1: extract features once
python 1_extract_features.py --dataset_dir /path/to/AFEW-VA

# Step 2: train temporal head
python 5_train.py

# Resume
python 5_train.py --resume
```

---

## Tips

- **GPU**: Both pipelines auto-detect CUDA. Mixed precision (`use_amp=True`) is on by default.
- **Memory**: Pipeline B is designed for ~20 GB GPUs. Pipeline A works on 24 GB+ with `batch_size=8`.
- **LoRA**: Only ~200K parameters added to the frozen backbone. Disable with `--no-use_lora` for a linear-probe baseline.
- **Reproducibility**: Override the global seed with `--seed`.
- **Legacy code**: Previous experimental implementations are in `legacy/` for reference.

---

## Citation

If you use this work, please cite:

```bibtex
@software{multimodal_emotion_understanding,
  author = {Bajaj, Aaryaman},
  title = {Multimodal Vision-Language Emotion Understanding},
  year = {2026},
  publisher = {GitHub},
  url = {https://github.com/Aaryaman3/multimodal-emotion-understanding}
}
```
