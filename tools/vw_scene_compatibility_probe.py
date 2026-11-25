from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import os

from tayvoriq_scene_revision_v1 import read_json, revise_export, _load_donor_stock, _render_captioned_clip, video_shape
from tayvoriq_cloud_render_safe import make_overlay

checkpoint = Path(sys.argv[1])
variants = read_json(checkpoint / "job.json")["variants"]
y, t = (variants[p]["render"]["asset_report"] for p in ("youtube_shorts", "tiktok"))
original = checkpoint / "short_youtube.mp4"
donor = checkpoint / "short_tiktok.mp4"
stock = {"source_media_url": "https://videos.pexels.com/video-files/33636879/14294210_2160_3838_24fps.mp4",
         "pexels_source_sha256": "e6953b17877e24a367835fd403eb92aecd4c74c8974b14de668fa895d43a57d9",
         "source_clip_sha256": "79c18d50e4a91a25ae894c228dd363a0dde04374d22e9ccb29cda69bed4adfe4"}
with TemporaryDirectory(dir=os.environ["RUNNER_TEMP"]) as tmp:
    work = Path(tmp)
    media = work / "donor.mp4"
    _load_donor_stock(stock, media)
    script = variants["youtube_shorts"]["text_package"]["scenes"][5]["spoken_chunk"]
    clip = _render_captioned_clip(work, original, y, 6, script, make_overlay, media)
    print("Input and captioned scene:", video_shape(original), video_shape(donor), video_shape(clip), flush=True)
    import json, subprocess
    import tayvoriq_scene_revision_v1 as scene_revision
    check_shape = scene_revision.video_shape
    def log_probe(path):
        try:
            return check_shape(path)
        except ValueError:
            probe = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0",
                      "-show_entries", "stream=width,height,nb_frames,start_pts,time_base,duration_ts,pix_fmt,avg_frame_rate,r_frame_rate",
                      "-of", "json", str(path)], text=True)
            print("Rejected video probe", path.name, json.loads(probe), flush=True)
            raise
    scene_revision.video_shape = log_probe
    evidence = revise_export(Path(os.environ["TAYVORIQ_MONEYPRINTERTURBO_ROOT"]), work/"project",
                             work, original, donor, y, t, (5,), work/"result.mp4")
    print("Compatible frame count and unchanged audio:", video_shape(work/"result.mp4"), evidence["audio_sha256"])
