"""Re-render the movie GIFs of the frozen results from their stored stacks (runs on GitHub Actions).

Only the GIF files change: photometry, stacks and results stay exactly as they were frozen.
The frames are drawn with the same code the app uses (movie.render_frames).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coldmovers import movie, pipeline, validation  # noqa: E402
from coldmovers.targets import Target  # noqa: E402

PRE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "precomputed")

for key in sorted(os.listdir(PRE)):
    outdir = os.path.join(PRE, key)
    view = pipeline.load(outdir)
    if view is None:
        continue
    target = Target.from_dict(view["target"])
    stacks = validation.load_stacks(outdir)
    marker = validation.marker_for(target, view["ref_wcs"])
    epochs = [dict(ep, stacks=stacks.get(ep["index"], {}),
                   counts={int(k): v for k, v in ep.get("counts", {}).items()}) for ep in view["epochs"]]
    track = pipeline.track_points(marker, view["epochs"])
    for det, name in sorted(view.get("gifs", {}).items()):
        pngs = movie.render_frames(epochs, int(det), marker, pipeline.epoch_title, track=track)
        if not pngs:
            print(key, name, "no frames, left as it was")
            continue
        with open(os.path.join(outdir, name), "wb") as fh:
            fh.write(movie.frames_to_gif(pngs))
        print(key, name, f"re-rendered ({len(pngs)} frames)")
