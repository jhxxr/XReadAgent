# A Minimal Study of Attention Mechanisms in Compact Transformer Architectures

**Authors**: Jane Doe, John Smith
**Year**: 2026
**Venue**: Workshop on Tiny Models (fictional, used only for smoke testing)

## Abstract

We present a small-scale empirical study of self-attention in compact
transformer models, focusing on the trade-off between model size and downstream
quality for resource-constrained settings. Using a two-layer encoder with
shared positional embeddings, we show that a careful choice of attention
projection rank and a lightweight model-distillation step recovers most of the
quality gap to a four-times-larger baseline. The setup is intentionally
minimal so the results are easy to reproduce on a single consumer GPU. This
paper exists primarily as a fixture for the XReadAgent smoke test; the
quantitative claims should not be taken as real research findings.

## Introduction

Large transformer models dominate state-of-the-art benchmarks across NLP, but
their inference cost is prohibitive on edge devices. A long line of work
explores compact alternatives — pruning, quantization, distillation — and a
parallel line investigates whether the attention mechanism itself can be made
cheaper without sacrificing the relational inductive bias that motivates it.
We study a particularly simple compromise: keep the attention operator
intact, but reduce its projection rank and combine it with a one-pass
distillation from a frozen larger teacher.

## Background

Self-attention computes pairwise interactions over token positions and adds
positional encoding to break the operator's permutation symmetry. We borrow
the standard scaled dot-product formulation and re-use sinusoidal positional
encodings rather than learned ones, mostly to remove a degree of freedom from
the search space. Prior work on low-rank attention (Linformer, Performer) and
on positional encoding alternatives (rotary, ALiBi) provides the obvious
contrast for our positioning.

## Method

Our model has two encoder layers. Each layer applies a multi-head
self-attention block with the query, key, and value projections rank-reduced
to ``r = d / 4`` where ``d`` is the hidden size. We then apply a feed-forward
block of half the usual hidden expansion factor. Training proceeds in two
stages: first a standard cross-entropy objective for one epoch on the task
data, then a model-distillation epoch where the student matches the teacher's
soft logits with temperature ``T = 4``. The teacher is a frozen
unmodified-rank transformer trained from scratch on the same data. We use
AdamW with a peak learning rate of ``1e-4`` and a 1k-step linear warmup.

## Experiments

We evaluate on a held-out classification split with 5 000 examples. The
compact model reaches 88.2 % accuracy versus the teacher's 91.0 %, recovering
roughly 70 % of the quality gap to a fully-trained large baseline. Inference
latency on a consumer CPU drops from 41 ms / example to 9 ms / example, a
4.5× speedup. We attribute the latency improvement primarily to the reduced
attention rank and the smaller feed-forward expansion, not to fewer encoder
layers per se.

## Conclusion

Carefully chosen low-rank self-attention plus a single-pass model-distillation
step is a sound starting point for tight inference budgets. Future work
includes evaluating rotary positional encoding in the same setup and pushing
the compression further with quantization-aware training.

## References

[1] Vaswani et al. (2017). *Attention Is All You Need.*
[2] Hinton et al. (2015). *Distilling the knowledge in a neural network.*
[3] Wang et al. (2020). *Linformer: Self-attention with linear complexity.*
