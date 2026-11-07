# RealESRGAN 4× restoration

Outputs larger than their bounded diffusion base require exactly
`RealESRGAN_x4plus.pth`, the general-photo model from the official
[xinntao/Real-ESRGAN v0.1.0 release](https://github.com/xinntao/Real-ESRGAN/releases/tag/v0.1.0).
This is not the anime variant or two passes of the 2× model. Weights are not
bundled or automatically downloaded. Verify the source of locally installed
weights before use; a matching filename alone is not provenance.

The controller checks ComfyUI's model options and node contracts before
submission. Missing 4× weights (including an installation with only x2plus)
defer the job with the required filename and no POST submission. There is no
silent 2× fallback.

## Base, intermediate and final dimensions

1. Diffusion generates an exact-aspect, multiple-of-eight base within the
   selected model profile's existing pixel budget.
2. RealESRGAN enlarges that decoded image fourfold in each dimension.
3. Lanczos resizes it to the exact requested native dimensions, with cropping
   disabled. Targets that already match their base omit both upscale stages.

For example, the SDXL 4544×1920 panorama uses a 1136×480 base and a
4544×1920 restored intermediate. This is workflow geometry, not a quality
measurement. Profile-driven extreme aspect ratios can still require final
enlargement; native output size does not mean native diffusion detail.

Independent landscape and portrait wallpapers use the same restoration stage.
Connected panoramas restore the shared canvas before the existing monitor crop
mapping. Layout, crop mapping, sampler, seed, diffusion budgets and safety guards
are unchanged. The legacy no-profile admission policy still rejects targets
larger than twice the base in either axis; changing that policy is separate work.

## Cost and acceptance

A 4× intermediate has more pixels than the previous 2× intermediate and may
require more time and memory. Existing VRAM gates do not prove every output will
fit. No performance improvement or live visual acceptance is claimed here.
Upscaling may improve apparent detail but can invent texture, ringing or
text-like artifacts; it cannot guarantee recovery of original fine detail.

After owner-approved installation, keep Auto off for the first single-monitor
preview. Verify the saved graph's model, base geometry, sampler and final size.
Compare against a 2× baseline only with matching checkpoint, prompt, seed and
base dimensions. Inspect native-scale crops and record measured elapsed time
and memory when available. Test panorama only if desired; this update does not
change the saved independent-layout preference.
