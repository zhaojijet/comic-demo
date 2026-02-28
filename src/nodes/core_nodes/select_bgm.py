from typing import Any, Dict
from pathlib import Path

import numpy as np
import random
import librosa

from nodes.core_nodes.base_node import BaseNode, NodeMeta
from nodes.node_state import NodeState
from nodes.node_schema import SelectBGMInput
from utils.element_filter import ElementFilter
from utils.recall import ComicDemoRecall
from utils.prompts import get_prompt
from utils.parse_json import parse_json_dict
from utils.register import NODE_REGISTRY

@NODE_REGISTRY.register()
class SelectBGMNode(BaseNode):
    meta = NodeMeta(
        name="select_bgm",
        description="Select appropriate BGM based on user requirements",
        node_id="select_bgm",
        node_kind="music_rec",
        require_prior_kind=[],
        default_require_prior_kind=[],
        next_available_node=["plan_timeline"],
    )

    input_schema = SelectBGMInput

    def __init__(self, server_cfg):
        super().__init__(server_cfg)
        self.element_filter = ElementFilter(json_path=f"{self.server_cfg.project.bgm_dir}/meta.json")
        self.vectorstore = ComicDemoRecall.build_vectorstore(self.element_filter.library)

    async def default_process(
        self,
        node_state: NodeState,
        inputs: Dict[str, Any],
    ) -> Any:
        node_state.node_summary.info_for_user("Failed to choose music")
        return {"bgm": {}}


    async def process(self, node_state: NodeState, inputs: Dict[str, Any]) -> Any:
        cfg = self.server_cfg
        user_request = inputs.get("user_request", "")
        filter_include = inputs.get("filter_include", {})
        filter_exclude = inputs.get("filter_exclude", {})
        bgm_info = await self.recommend(node_state, user_request, filter_include, filter_exclude)
        if not bgm_info:
            return {"bgm": {}}

        result = self.analyze_music_metrics(bgm_info=bgm_info, sr=cfg.select_bgm.sample_rate, hop_length=cfg.select_bgm.hop_length, frame_length=cfg.select_bgm.frame_length)
        if result.get("path"):
            node_state.node_summary.info_for_user(f"Successfully choose music", preview_urls = [result.get("path")])
        else:
            node_state.node_summary.info_for_user("Failed to choose music")
        return {"bgm": result}


    async def recommend(
            self, 
            node_state: NodeState,
            user_request: str, 
            filter_include: Dict={}, 
            filter_exclude: Dict={}
        ):

        # Step1: Check resources
        bgm_dir: Path = self.server_cfg.project.bgm_dir.expanduser().resolve()
        if not bgm_dir.exists():
            raise FileNotFoundError(f"bgm_dir not found: {bgm_dir}")
        if not bgm_dir.is_dir():
            raise NotADirectoryError(f"bgm_dir is not a directory: {bgm_dir}")
        
        # Step2: Full Recall
        candidates = ComicDemoRecall.query_top_n(self.vectorstore, query=user_request)

        # Step3: Filter tags
        candidates = self.element_filter.filter(candidates, filter_include, filter_exclude)
        if not candidates:
            raise FileNotFoundError(f"No audio files found in: {bgm_dir}")
        
        # Step4: LLM Sampling
        llm = node_state.llm
        system_prompt = get_prompt("select_bgm.system", lang=node_state.lang)
        user_prompt = get_prompt("select_bgm.user", lang=node_state.lang, candidates=candidates, user_request=user_request)
        raw = await llm.complete(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.1,
            top_p=0.9,
            max_tokens=2048,
            model_preferences=None,
        )
        try:
            selected_json = parse_json_dict(raw)
        except:
            selected_json = (raw or "").strip() if raw else "Error: Unable to parse the model output"
            node_state.node_summary.add_error(selected_json)
        
        if not isinstance(selected_json, Dict) or 'path' not in selected_json:
            # Demotion select the first one of candidates
            selected_json = candidates[0]
        
        return selected_json
    

    def analyze_music_metrics(
        self,
        bgm_info: Dict,
        sr: int = 22050,
        hop_length = 2048,
        frame_length = 2048,

    ) -> dict[str, Any]:
        path = Path(bgm_info.get("path"))
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        
        y, sample_rate = self._load_audio_mono(path, sr=sr)
        duration = int(librosa.get_duration(y=y, sr=sample_rate) * 1000)

        if y.size < frame_length:
            raise RuntimeError("The selected background music is too short.")
        
        onset_env = librosa.onset.onset_strength(y=y, sr=sample_rate, hop_length=hop_length)
        bpm, beat_frames = librosa.beat.beat_track(
            onset_envelope=onset_env,
            sr=sr,
            hop_length=hop_length,
            units="frames",
        )

        bpm_val = float(np.atleast_1d(bpm)[0])

        beat_frames = np.asarray(beat_frames, dtype=int)

        beat_times = self._compute_accent_beats(y=y, sr=sample_rate, beat_frames=beat_frames, hop_length=hop_length)

        rms = librosa.feature.rms(
            y=y,
            frame_length=frame_length,
            hop_length=hop_length
        )[0]

        energy_mean = float(np.mean(rms))

        rms_db = librosa.amplitude_to_db(np.maximum(rms, 1e-10), ref=1.0)
        energy_mean_db = float(np.mean(rms_db))

        lo = float(np.percentile(rms_db, 10.0))
        hi = float(np.percentile(rms_db, 95.0))
        dynamic_range_db = float(hi - lo)

        return {
            "bgm_id": bgm_info.get("id"),
            "path": str(path),
            "duration": duration,
            "sample_rate": sample_rate,
            "bpm": bpm_val,
            "beats": beat_times,
            "energy_mean": energy_mean,
            "energy_mean_db": energy_mean_db,
            "dynamic_range_db": dynamic_range_db,
        }


    @staticmethod
    def _load_audio_mono(path: Path, sr: int) -> tuple[np.ndarray, int]:

        try:
            y, sr_out = librosa.load(path, sr=sr, mono=True)
            return y.astype(np.float32, copy=False), int(sr_out)
        except Exception as e1:

            # Librosa failed to read. ffmpeg is used as a fallback
            import os
            import subprocess
            import tempfile

            tmp_wav = None
            try: 
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    tmp_wav = tmp.name
                
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-i", str(path),
                    "-ac", "1",
                    "-ar", str(sr),
                    "-vn",
                    tmp_wav,
                ]
                subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

                y, sr_out = librosa.load(tmp_wav, sr=sr, mono=True)
                return y.astype(np.float32, copy=False), int(sr_out)
            
            except FileNotFoundError as e_ffmpeg:
                raise RuntimeError(
                    f"The audio cannot be loaded and ffmpeg is not found."
                ) from e_ffmpeg

            except Exception as e2:
                raise RuntimeError(
                    f"The audio cannot be loaded: {type(e1).__name__}: {e1}"
                    f"Ffmpeg error: {type(e2).__name__}: {e2}"
                ) from e2
            finally:
                if tmp_wav is not None:
                    try:
                        os.remove(tmp_wav)
                    except Exception:
                        pass


    @staticmethod
    def _compute_accent_beats(
        y: np.ndarray,
        sr: int,
        beat_frames: np.ndarray,
        hop_length: int,
        top_pct: float = 70.0,          
        min_sep_beats: int = 1,         # Min beat separation: 1 prevents selecting adjacent beats
        use_percussive: bool = True,    # Calculate onset strength from percussive component
        local_norm_win: int = 8,        # Window size for local normalization (measured in beats)
        require_local_peak: bool = True # Only retain onsets that are local maxima
    ) -> list[float]:
        """
        Calculate timestamps of the top `top_pct` percent of drum beats by intensity
        """

        if beat_frames.size == 0:
            return []

        # 1) Use percussive version for onset envelope
        y_for_onset = librosa.effects.percussive(y) if use_percussive else y
        onset_env = librosa.onset.onset_strength(y=y_for_onset, sr=sr, hop_length=hop_length)

        # 2) Use onset strength at each beat time as beat strength
        beat_frames_clip = np.clip(beat_frames.astype(int), 0, len(onset_env) - 1)
        strength = onset_env[beat_frames_clip].astype(np.float64)  # shape (n_beats,)

        # 3) Local normalization: prevent louder sections from dominating beat selection
        if strength.size >= 3 and local_norm_win >= 3:
            w = int(local_norm_win)
            kernel = np.ones(w, dtype=np.float64) / w
            local_mean = np.convolve(strength, kernel, mode="same")
            strength_norm = strength / (local_mean + 1e-8)
        else:
            strength_norm = strength.copy()

        # 4) Select beats in the top top_pct percentile
        thr = float(np.percentile(strength_norm, 100.0 - top_pct))
        cand = np.where(strength_norm >= thr)[0]  # indices into beats

        # 5) Retain only local peaks to prevent selecting many beats during plateaus
        if require_local_peak and cand.size > 0 and strength_norm.size >= 3:
            is_peak = np.zeros_like(strength_norm, dtype=bool)
            is_peak[1:-1] = (strength_norm[1:-1] >= strength_norm[:-2]) & (strength_norm[1:-1] >= strength_norm[2:])
            is_peak[0] = strength_norm[0] >= strength_norm[1]
            is_peak[-1] = strength_norm[-1] >= strength_norm[-2]
            cand = cand[is_peak[cand]]

        # 6) Minimum separation suppression
        selected = []
        if cand.size > 0:
            order = cand[np.argsort(-strength_norm[cand])]
            suppressed = np.zeros(strength_norm.size, dtype=bool)

            for idx in order:
                if suppressed[idx]:
                    continue
                selected.append(int(idx))
                lo = max(0, idx - min_sep_beats)
                hi = min(strength_norm.size, idx + min_sep_beats + 1)
                suppressed[lo:hi] = True

        selected = np.array(sorted(selected), dtype=int)

        accent_frames = beat_frames[selected]
        accent_times = librosa.frames_to_time(accent_frames, sr=sr, hop_length=hop_length).tolist()

        accent_times_ms = [round(x * 1000) for x in accent_times]

        return accent_times_ms
