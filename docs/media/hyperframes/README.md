# Capability demo video

Source project for the README's capability-demo video, authored as HTML/CSS and rendered to MP4 via [HyperFrames](https://github.com/heygen-com/hyperframes) (`npx hyperframes`, no local install needed).

- `demo/index.html` is the whole composition: six timed scenes (title, belief statement, three real screenshot panels, closing stats), animated with GSAP.
- `demo/assets/` holds the real screenshots used in the panels (captured from a live, running instance).

To re-render after editing `demo/index.html`:

```bash
cd demo
npm run check   # lint + runtime + layout + motion + contrast
npm run render  # -> capability-demo.mp4
ffmpeg -y -i capability-demo.mp4 -vf "fps=12,scale=780:-1:flags=lanczos,split[s0][s1];[s0]palettegen=stats_mode=diff[p];[s1][p]paletteuse=dither=bayer" capability-demo.gif
cp capability-demo.mp4 capability-demo.gif ../
```

The two files at `docs/media/capability-demo.{mp4,gif}` (one level up) are the ones actually embedded in the root `README.md`.
