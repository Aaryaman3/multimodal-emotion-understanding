"""
Model architecture: CLIP + LoRA + Temporal Head + Regression Head
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Optional, Tuple
import open_clip


class LoRALayer(nn.Module):
    """Low-Rank Adaptation layer for linear projections."""
    def __init__(self, in_features: int, out_features: int, rank: int = 8, alpha: int = 16):
        super().__init__()
        self.rank = rank
        self.alpha = alpha
        self.scaling = alpha / rank

        # A: gaussian init, B: zero init → delta_W starts at zero
        self.lora_A = nn.Parameter(torch.randn(in_features, rank) * (1.0 / rank ** 0.5))
        self.lora_B = nn.Parameter(torch.zeros(rank, out_features))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return (x @ self.lora_A @ self.lora_B) * self.scaling


class LoRALinear(nn.Module):
    """
    Wraps an existing nn.Linear and adds a LoRA delta on top.
    The original weight stays frozen; only lora_A and lora_B train.
    """
    def __init__(self, linear: nn.Linear, rank: int = 8, alpha: int = 16):
        super().__init__()
        self.linear = linear          # frozen original
        self.lora = LoRALayer(
            linear.in_features, linear.out_features, rank=rank, alpha=alpha
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.linear(x) + self.lora(x)


class FrameProjector(nn.Module):
    """Project frame features into a shared embedding space."""
    def __init__(self, input_dim: int, hidden_dim: int, output_dim: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim),
            nn.Linear(hidden_dim, output_dim)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return F.normalize(self.net(x), p=2, dim=-1)


class TemporalHead(nn.Module):
    """Aggregate frame embeddings over time into a single clip embedding."""
    def __init__(self, input_dim: int, output_dim: int, use_transformer: bool = False):
        super().__init__()
        self.use_transformer = use_transformer

        if use_transformer:
            self.transformer = nn.TransformerEncoderLayer(
                d_model=input_dim, nhead=4, dim_feedforward=input_dim * 2,
                dropout=0.1, batch_first=True
            )

        self.projection = nn.Linear(input_dim, output_dim)

    def forward(self, z_t: torch.Tensor) -> torch.Tensor:
        if self.use_transformer:
            z_t = self.transformer(z_t)
        g = z_t.mean(dim=1)
        return F.normalize(self.projection(g), p=2, dim=-1)


class RegressionHead(nn.Module):
    """Predict frame-level valence and arousal from embeddings."""
    def __init__(self, input_dim: int, hidden_dim: int = 64):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden_dim, 2)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class TemporalEmotionModel(nn.Module):
    """
    Full pipeline: frozen CLIP backbone → LoRA adapters on Q/V projections
    → frame-level projector → temporal aggregation → regression head.
    """
    def __init__(self, config):
        super().__init__()
        self.config = config

        # Load CLIP (backbone stays frozen)
        self.clip_model, _, _ = open_clip.create_model_and_transforms(
            config.clip_model, pretrained=config.clip_pretrained
        )
        for param in self.clip_model.parameters():
            param.requires_grad = False

        # Inject LoRA into the last transformer block's Q and V projections
        self.lora_q: Optional[LoRALinear] = None
        self.lora_v: Optional[LoRALinear] = None
        if config.use_lora:
            self._inject_lora()

        # Downstream heads
        self.frame_projector = FrameProjector(
            config.feature_dim, config.hidden_dim, config.projection_dim
        )
        self.temporal_head = TemporalHead(
            config.projection_dim, config.projection_dim, use_transformer=False
        )
        self.regression_head = RegressionHead(config.projection_dim, hidden_dim=64)

        # Memory queue for MoCo-style negatives
        self.register_buffer(
            "memory_queue",
            F.normalize(torch.randn(config.memory_queue_size, config.projection_dim), p=2, dim=1)
        )
        self.register_buffer("queue_ptr", torch.zeros(1, dtype=torch.long))

    # ------------------------------------------------------------------
    # LoRA injection
    # ------------------------------------------------------------------

    def _inject_lora(self):
        """
        Replace the Q and V linear projections in the last ViT block with
        LoRALinear wrappers so gradients actually flow through the LoRA matrices.

        open_clip uses a fused in_proj_weight of shape [3*d, d] for Q, K, V.
        We extract Q and V slices into standalone nn.Linear modules, freeze them,
        wrap each with LoRALinear, and patch the attention forward to add the
        LoRA delta into the residual stream after projection.
        """
        visual = self.clip_model.visual
        if not hasattr(visual, "transformer"):
            print("Warning: CLIP visual encoder has no .transformer — LoRA skipped.")
            return

        last_block = visual.transformer.resblocks[-1]
        attn = last_block.attn
        d_model = attn.in_proj_weight.shape[1]
        has_bias = attn.in_proj_bias is not None

        # Build frozen stand-alone linears for Q and V
        q_linear = nn.Linear(d_model, d_model, bias=has_bias)
        v_linear = nn.Linear(d_model, d_model, bias=has_bias)

        with torch.no_grad():
            q_linear.weight.copy_(attn.in_proj_weight[:d_model])
            v_linear.weight.copy_(attn.in_proj_weight[2 * d_model:])
            if has_bias:
                q_linear.bias.copy_(attn.in_proj_bias[:d_model])
                v_linear.bias.copy_(attn.in_proj_bias[2 * d_model:])

        for p in q_linear.parameters():
            p.requires_grad = False
        for p in v_linear.parameters():
            p.requires_grad = False

        self.lora_q = LoRALinear(q_linear, rank=self.config.lora_rank, alpha=self.config.lora_alpha)
        self.lora_v = LoRALinear(v_linear, rank=self.config.lora_rank, alpha=self.config.lora_alpha)

        # Patch attention forward: add LoRA deltas for Q and V into the output
        _lora_q = self.lora_q
        _lora_v = self.lora_v
        _orig_forward = attn.forward
        _out_proj = attn.out_proj

        def lora_patched_forward(query, key, value, **kwargs):
            out, attn_weights = _orig_forward(query, key, value, **kwargs)
            # Compute LoRA deltas in Q/V space and project back through out_proj
            q_delta = _lora_q.lora(query)   # [seq, B, d] or [B, seq, d]
            v_delta = _lora_v.lora(value)
            lora_signal = F.linear(q_delta + v_delta, _out_proj.weight)
            out = out + lora_signal
            return out, attn_weights

        attn.forward = lora_patched_forward

    # ------------------------------------------------------------------
    # Forward pass
    # ------------------------------------------------------------------

    def encode_frames(self, images: torch.Tensor) -> torch.Tensor:
        """Run frozen CLIP encoder over a batch of frames."""
        if images.ndim == 5:
            B, L = images.shape[:2]
            images = images.view(B * L, *images.shape[2:])
            reshape = (B, L)
        else:
            reshape = None

        with torch.no_grad():
            features = self.clip_model.encode_image(images)

        if reshape is not None:
            features = features.view(*reshape, -1)

        return features

    def forward(
        self,
        images: torch.Tensor,
        return_regression: bool = False
    ) -> Tuple[torch.Tensor, torch.Tensor, Optional[torch.Tensor]]:
        features = self.encode_frames(images)          # [B, L, D]
        z_t = self.frame_projector(features)           # [B, L, proj_dim]
        g = self.temporal_head(z_t)                    # [B, proj_dim]
        va_pred = self.regression_head(z_t) if return_regression else None
        return z_t, g, va_pred

    # ------------------------------------------------------------------
    # Memory queue
    # ------------------------------------------------------------------

    @torch.no_grad()
    def update_memory_queue(self, embeddings: torch.Tensor):
        batch_size = embeddings.shape[0]
        ptr = int(self.queue_ptr)
        end = ptr + batch_size

        if end <= self.config.memory_queue_size:
            self.memory_queue[ptr:end] = embeddings
        else:
            tail = self.config.memory_queue_size - ptr
            self.memory_queue[ptr:] = embeddings[:tail]
            self.memory_queue[:batch_size - tail] = embeddings[tail:]

        self.queue_ptr[0] = end % self.config.memory_queue_size

    # ------------------------------------------------------------------
    # Parameter groups
    # ------------------------------------------------------------------

    def get_trainable_parameters(self, stage: str = "pretrain"):
        params = []

        if self.config.use_lora and self.lora_q is not None:
            params += [
                {"params": self.lora_q.lora.parameters()},
                {"params": self.lora_v.lora.parameters()},
            ]

        if stage == "pretrain":
            params += [
                {"params": self.frame_projector.parameters()},
                {"params": self.temporal_head.parameters()},
            ]
        elif stage == "finetune":
            params += [
                {"params": self.temporal_head.parameters()},
                {"params": self.regression_head.parameters()},
            ]
        else:
            raise ValueError(f"Unknown training stage: {stage!r}")

        return params