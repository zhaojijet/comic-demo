from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Tuple

from config import Settings
from config import PlanTimelineConfig
from nodes.node_state import NodeState
from nodes.core_nodes.base_node import BaseNode, NodeMeta
from nodes.node_schema import PlanTimelineInput
from utils.register import NODE_REGISTRY

# =========================
# Constants (no magic numbers)
# =========================
Milliseconds = int

DEFAULT_RANDOM_SEED = 42

SECONDS_PER_MINUTE = 60.0
MILLISECONDS_PER_SECOND = 1000.0

SNAP_SAFETY_MAX_STEPS = 10_000
BINARY_SEARCH_ITERATIONS = 50

RATIO_GROWTH_FACTOR = 2.0
RATIO_GROWTH_MAX = 10.0

MIN_SUBTITLE_WEIGHT = 1
CENTER_ALIGN_DIVISOR = 2.0


@dataclass(frozen=True)
class BeatTrack:
    """Beat-related information derived from background music (BGM)."""

    beat_timestamps_ms: List[Milliseconds]
    beat_durations_ms: List[Milliseconds]
    music_duration_ms: Milliseconds


class TimelinePlanner:
    """
    Pure timeline planning logic extracted from PlanTimelineNode for:
    - clearer separation of concerns
    - better readability
    - easier unit testing
    """

    def __init__(self, config: PlanTimelineConfig, *, random_seed: int = DEFAULT_RANDOM_SEED) -> None:
        self._config = config
        self._random_generator = random.Random(random_seed)

    def plan(
        self,
        *,
        media: List[Dict[str, Any]],
        clips: List[Dict[str, Any]],
        groups: List[Dict[str, Any]],
        group_scripts: List[Dict[str, Any]],
        voiceovers: List[Dict[str, Any]],
        background_music: Optional[Dict[str, Any]],
        use_beats: bool,
    ) -> Dict[str, Any]:
        """Plan full timeline tracks: video/subtitles/voiceover/bgm."""
        media_by_media_id = self._build_item_index(media, id_key="media_id")
        clips_by_clip_id = self._build_item_index(clips, id_key="clip_id")
        script_by_group_id = self._build_item_index(group_scripts, id_key="group_id")
        voiceover_by_group_id = self._build_item_index(voiceovers, id_key="group_id")

        beat_track = self._build_beat_track(background_music, use_beats=use_beats)

        music_offset_ms, start_beat_index = self._compute_title_music_offset(
            beat_durations_ms=beat_track.beat_durations_ms,
            music_duration_ms=beat_track.music_duration_ms,
            use_beats=use_beats,
        )

        video_segments, group_states, total_duration_ms, _end_beat_index = self._build_video_track(
            groups=groups,
            clips_by_clip_id=clips_by_clip_id,
            media_by_media_id=media_by_media_id,
            script_by_group_id=script_by_group_id,
            voiceover_by_group_id=voiceover_by_group_id,
            background_music=background_music,
            beat_durations_ms=beat_track.beat_durations_ms,
            start_beat_index=start_beat_index,
            use_beats=use_beats,
        )

        voiceover_segments = self._build_voiceover_track(groups=groups, group_states=group_states)
        subtitle_segments = self._build_subtitle_track(groups=groups, group_states=group_states)
        bgm_segments = self._build_bgm_track(
            background_music=background_music,
            total_duration_ms=total_duration_ms,
            music_offset_ms=music_offset_ms,
        )

        return {
            "tracks": {
                "video": video_segments,
                "subtitles": subtitle_segments,
                "voiceover": voiceover_segments,
                "bgm": bgm_segments,
            }
        }

    # -----------------------------
    # Track builders
    # -----------------------------
    def _build_video_track(
        self,
        *,
        groups: List[Dict[str, Any]],
        clips_by_clip_id: Mapping[str, Dict[str, Any]],
        media_by_media_id: Mapping[str, Dict[str, Any]],
        script_by_group_id: Mapping[str, Dict[str, Any]],
        voiceover_by_group_id: Mapping[str, Dict[str, Any]],
        background_music: Optional[Dict[str, Any]],
        beat_durations_ms: List[Milliseconds],
        start_beat_index: int,
        use_beats: bool,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]], Milliseconds, int]:
        video_segments: List[Dict[str, Any]] = []
        group_states: Dict[str, Dict[str, Any]] = {}

        timeline_cursor_ms: Milliseconds = 0
        residual_ms: Milliseconds = 0  # preserved for future improvements; legacy code kept it but didn't update it.

        beat_index = int(start_beat_index)

        for group in groups:
            group_id = self._to_str_id(group.get("group_id"))
            clip_ids = [self._to_str_id(cid) for cid in (group.get("clip_ids", []) or [])]
            if not clip_ids:
                raise ValueError(
                    f"group {group_id} has no clip_ids, please check the result of 'group_clips' node"
                )

            clip_items: List[Dict[str, Any]] = []
            for clip_id in clip_ids:
                if clip_id not in clips_by_clip_id:
                    raise KeyError(
                        f"group {group_id} references missing clip_id={clip_id}, "
                        "please check the result of 'group_clips' and 'split_shots' node"
                    )
                clip_items.append(clips_by_clip_id[clip_id])

            group_script = script_by_group_id.get(group_id)
            group_voiceover = voiceover_by_group_id.get(group_id)

            # Case A: no script, no voiceover, and no beat snapping -> concatenate clips as-is.
            if not group_script and not group_voiceover and (not background_music or not use_beats):
                group_start_ms = timeline_cursor_ms
                first_clip_source_duration_ms: Milliseconds = 0

                for index_in_group, clip in enumerate(clip_items):
                    clip_id = self._to_str_id(clip.get("clip_id"))
                    clip_kind = str(clip.get("kind", "video"))

                    source_start_ms, source_end_ms, source_duration_ms = self._full_source_window_and_duration_ms(
                        clip
                    )
                    if index_in_group == 0:
                        first_clip_source_duration_ms = source_duration_ms

                    segment_start_ms = timeline_cursor_ms
                    segment_end_ms = segment_start_ms + source_duration_ms

                    video_segments.append(
                        {
                            "clip_id": clip_id,
                            "group_id": group_id,
                            "kind": clip_kind,
                            "path": clip.get("path"),
                            "fps": clip.get("fps"),
                            "source_path": self._resolve_source_path(
                                clip=clip, media_by_media_id=media_by_media_id
                            ),
                            "source_window": {"start": source_start_ms, "end": source_end_ms},
                            # NOTE: the original code used {"start": seg_end, "end": seg_end} here,
                            # which produces a 0-length window. This is almost certainly a typo.
                            "timeline_window": {"start": segment_start_ms, "end": segment_end_ms},
                            "playback_rate": 1.0,
                        }
                    )
                    timeline_cursor_ms = segment_end_ms

                group_end_ms = timeline_cursor_ms
                group_states[group_id] = {
                    "group_id": group_id,
                    "start": group_start_ms,
                    "end": group_end_ms,
                    "duration": group_end_ms - group_start_ms,
                    "first_clip_duration": first_clip_source_duration_ms,
                }
                continue

            # Case B: voiceover duration is authoritative; otherwise estimate by text length.
            if group_voiceover and group_voiceover.get("duration", 0) > 0:
                narration_duration_ms: Milliseconds = int(group_voiceover.get("duration", 0))
            else:
                narration_duration_ms = self._estimate_group_duration_from_text_ms(group_script)

            group_target_duration_ms: Milliseconds = narration_duration_ms + int(self._config.group_margin_over_voiceover)
            group_target_duration_ms = max(
                group_target_duration_ms, len(clip_items) * int(self._config.min_clip_duration)
            )

            if use_beats and background_music:
                durations_ms, beat_index = self._allocate_clip_durations_using_beats(
                    clip_items=clip_items,
                    group_target_ms=group_target_duration_ms,
                    beat_durations_ms=beat_durations_ms,
                    start_beat_index=beat_index,
                    start_residual_ms=residual_ms,
                )
            else:
                durations_ms = self._allocate_clip_durations_without_beats(
                    clip_items=clip_items, group_target_ms=group_target_duration_ms
                )

            group_start_ms = timeline_cursor_ms
            first_clip_planned_duration_ms: Milliseconds = durations_ms[0] if durations_ms else 0

            for clip, planned_duration_ms in zip(clip_items, durations_ms):
                clip_id = clip.get("clip_id")  # keep legacy behavior (may be int)
                clip_kind = str(clip.get("kind", "video")).lower()

                segment_start_ms = timeline_cursor_ms
                segment_end_ms = segment_start_ms + int(planned_duration_ms)

                source_start_ms, source_end_ms, source_available_ms = self._full_source_window_and_duration_ms(clip)
                playback_rate = 1.0

                if clip_kind == "video":
                    if planned_duration_ms > source_available_ms:
                        playback_rate = (source_available_ms / planned_duration_ms) if planned_duration_ms > 0 else 1.0
                        source_window_start_ms, source_window_end_ms = source_start_ms, source_end_ms
                    else:
                        source_window_start_ms, source_window_end_ms = self._choose_source_window_for_timeline_duration_ms(
                            clip=clip, used_timeline_duration_ms=int(planned_duration_ms)
                        )
                else:
                    # image (and other non-video kinds): use from src_start for the planned duration
                    source_window_start_ms, source_window_end_ms = (
                        source_start_ms,
                        source_start_ms + int(planned_duration_ms),
                    )

                video_segments.append(
                    {
                        "clip_id": clip_id,
                        "group_id": group_id,
                        "kind": clip_kind,
                        "path": clip.get("path"),
                        "orig_path": clip.get("orig_path"),
                        "fps": clip.get("fps"),
                        "size": clip.get("size"),
                        "source_path": self._resolve_source_path(
                            clip=clip, media_by_media_id=media_by_media_id
                        ),
                        "source_window": {
                            "start": source_window_start_ms,
                            "end": source_window_end_ms,
                            "duration": source_window_end_ms - source_window_start_ms,
                        },
                        "timeline_window": {
                            "start": segment_start_ms,
                            "end": segment_end_ms,
                            "duration": segment_end_ms - segment_start_ms,
                        },
                        "playback_rate": playback_rate,
                    }
                )

                timeline_cursor_ms = segment_end_ms

            group_end_ms = timeline_cursor_ms
            group_states[group_id] = {
                "group_id": group_id,
                "start": group_start_ms,
                "end": group_end_ms,
                "duration": group_end_ms - group_start_ms,
                "first_clip_duration": int(first_clip_planned_duration_ms),
                "n_clips": len(clip_items),
                "narration_duration": narration_duration_ms,
                "group_margin": int(self._config.group_margin_over_voiceover),
                "voiceover": group_voiceover,
                "script": group_script,
            }

        total_duration_ms = timeline_cursor_ms
        return video_segments, group_states, total_duration_ms, beat_index

    def _build_voiceover_track(
        self, *, groups: List[Dict[str, Any]], group_states: MutableMapping[str, Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        voiceover_segments: List[Dict[str, Any]] = []

        for group in groups:
            group_id = self._to_str_id(group.get("group_id", ""))
            state = group_states.get(group_id)
            if not state:
                continue

            voiceover_item = state.get("voiceover")
            if not voiceover_item:
                continue

            voiceover_duration_ms = int(voiceover_item.get("duration", 0))
            if voiceover_duration_ms <= 0:
                continue

            group_start_ms = int(state.get("start", 0))
            group_end_ms = int(state.get("end", 0))
            group_duration_ms = group_end_ms - group_start_ms

            slack_ms = max(0, group_duration_ms - voiceover_duration_ms)

            start_offset_ms = slack_ms / CENTER_ALIGN_DIVISOR
            voiceover_start_ms = group_start_ms + start_offset_ms
            voiceover_end_ms = voiceover_start_ms + voiceover_duration_ms

            voiceover_segments.append(
                {
                    "group_id": group_id,
                    "voiceover_id": voiceover_item.get("voiceover_id"),
                    "path": voiceover_item.get("path"),
                    "source_window": {"start": 0, "end": voiceover_duration_ms, "duration": voiceover_duration_ms},
                    "timeline_window": {
                        "start": voiceover_start_ms,
                        "end": voiceover_end_ms,
                        "duration": voiceover_duration_ms,
                    },
                }
            )

            state["voiceover_timeline"] = {
                "start": voiceover_start_ms,
                "end": voiceover_end_ms,
                "duration": voiceover_duration_ms,
            }

        return voiceover_segments

    def _build_subtitle_track(
        self, *, groups: List[Dict[str, Any]], group_states: Mapping[str, Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        subtitle_segments: List[Dict[str, Any]] = []

        for group in groups:
            group_id = self._to_str_id(group.get("group_id", ""))
            state = group_states.get(group_id)
            if not state:
                continue

            # NOTE: original code used default "" then script.get(...) -> may crash.
            group_script = state.get("script") or {}
            subtitle_units = group_script.get("subtitle_units", []) if isinstance(group_script, dict) else []
            if not subtitle_units:
                continue

            group_start_ms = int(state.get("start", 0))
            group_end_ms = int(state.get("end", 0))
            voiceover_timeline = state.get("voiceover_timeline")

            if voiceover_timeline is not None:
                voiceover_start_ms = voiceover_timeline["start"]
                voiceover_end_ms = voiceover_timeline["end"]

                if not (group_start_ms <= voiceover_start_ms <= voiceover_end_ms <= group_end_ms):
                    subtitle_start_ms = group_start_ms
                    subtitle_end_ms = group_end_ms
                else:
                    subtitle_start_ms = int((group_start_ms + voiceover_start_ms) / CENTER_ALIGN_DIVISOR)
                    subtitle_end_ms = int((voiceover_end_ms + group_end_ms) / CENTER_ALIGN_DIVISOR)
            else:
                subtitle_start_ms = group_start_ms
                subtitle_end_ms = group_end_ms

            subtitle_duration_ms = subtitle_end_ms - subtitle_start_ms

            unit_texts: List[str] = [str(u.get("text") or "") for u in subtitle_units]
            unit_weights: List[int] = [max(MIN_SUBTITLE_WEIGHT, len(text.strip())) for text in unit_texts]
            total_weight = sum(unit_weights)

            unit_durations_ms: List[Milliseconds] = []
            accumulated_ms: Milliseconds = 0
            for i, weight in enumerate(unit_weights):
                if i == len(unit_weights) - 1:
                    duration_ms = max(0, subtitle_duration_ms - accumulated_ms)
                else:
                    duration_ms = (subtitle_duration_ms * weight) // total_weight if total_weight > 0 else 0
                    accumulated_ms += int(duration_ms)
                unit_durations_ms.append(int(duration_ms))

            subtitle_cursor_ms = subtitle_start_ms
            for unit, text, duration_ms in zip(subtitle_units, unit_texts, unit_durations_ms):
                if duration_ms <= 0:
                    continue
                segment_start_ms = subtitle_cursor_ms
                segment_end_ms = subtitle_cursor_ms + int(duration_ms)
                subtitle_cursor_ms = segment_end_ms

                subtitle_segments.append(
                    {
                        "group_id": group_id,
                        "unit_id": unit.get("unit_id"),
                        "index_in_group": unit.get("index_in_group"),
                        "text": text,
                        "timeline_window": {"start": segment_start_ms, "end": segment_end_ms},
                    }
                )

        return subtitle_segments

    def _build_bgm_track(
        self,
        *,
        background_music: Optional[Dict[str, Any]],
        total_duration_ms: Milliseconds,
        music_offset_ms: Milliseconds,
    ) -> List[Dict[str, Any]]:
        bgm_segments: List[Dict[str, Any]] = []
        if not background_music:
            return bgm_segments

        music_duration_ms = int(background_music.get("duration", 0))
        if music_duration_ms <= 0:
            return bgm_segments

        timeline_cursor_ms: Milliseconds = 0
        source_cursor_ms: Milliseconds = int(music_offset_ms)
        loop_index = 0

        while timeline_cursor_ms < total_duration_ms:
            remaining_timeline_ms = total_duration_ms - timeline_cursor_ms
            remaining_source_ms = max(0, music_duration_ms - source_cursor_ms)

            if remaining_source_ms <= 0:
                source_cursor_ms = 0
                loop_index += 1
                continue

            segment_duration_ms = min(remaining_timeline_ms, remaining_source_ms)
            if segment_duration_ms <= 0:
                break

            bgm_segments.append(
                {
                    "bgm_id": background_music.get("bgm_id"),
                    "path": background_music.get("path"),
                    "source_window": {"start": source_cursor_ms, "end": source_cursor_ms + segment_duration_ms},
                    "loop_idx": loop_index,
                }
            )

            timeline_cursor_ms += segment_duration_ms
            source_cursor_ms += segment_duration_ms

            if timeline_cursor_ms < total_duration_ms and source_cursor_ms >= music_duration_ms:
                source_cursor_ms = 0
                loop_index += 1

        return bgm_segments

    # -----------------------------
    # Beats & title alignment
    # -----------------------------
    def _build_beat_track(self, background_music: Optional[Dict[str, Any]], *, use_beats: bool) -> BeatTrack:
        if not use_beats or not background_music:
            return BeatTrack(beat_timestamps_ms=[], beat_durations_ms=[], music_duration_ms=0)

        music_duration_ms = int(background_music.get("duration", 0))
        beat_timestamps_ms = self._build_beat_timestamps_from_music_ms(background_music)
        beat_durations_ms = self._convert_beat_timestamps_to_durations_ms(
            beat_timestamps_ms=beat_timestamps_ms, music_duration_ms=music_duration_ms
        )

        return BeatTrack(
            beat_timestamps_ms=beat_timestamps_ms,
            beat_durations_ms=beat_durations_ms,
            music_duration_ms=music_duration_ms,
        )

    def _compute_title_music_offset(
        self, *, beat_durations_ms: List[Milliseconds], music_duration_ms: Milliseconds, use_beats: bool
    ) -> Tuple[Milliseconds, int]:
        """
        Compute the BGM source offset so that the title ends on a beat.

        NOTE:
        - The original code assumes beat_durations_ms is non-empty; otherwise modulo would crash.
          Here we guard against empty beats (safer for open-source usage).
        """
        music_offset_ms: Milliseconds = 0
        beat_index = 0

        if not use_beats:
            return music_offset_ms, beat_index

        title_duration_ms = int(getattr(self._config, "title_duration", 0))
        if title_duration_ms <= 0 or music_duration_ms <= 0 or not beat_durations_ms:
            return music_offset_ms, beat_index

        if bool(getattr(self._config, "bgm_loop", False)):
            title_duration_ms = title_duration_ms % music_duration_ms
        else:
            title_duration_ms = min(title_duration_ms, music_duration_ms)

        cumulative_ms: Milliseconds = 0
        duration_index = 0
        while duration_index < len(beat_durations_ms) and cumulative_ms < title_duration_ms:
            cumulative_ms += int(beat_durations_ms[duration_index])
            duration_index += 1

        music_offset_ms = max(0, cumulative_ms - title_duration_ms)
        beat_index = duration_index % len(beat_durations_ms)
        return int(music_offset_ms), int(beat_index)

    # -----------------------------
    # Shared helpers (indexing, parsing, math)
    # -----------------------------
    @staticmethod
    def _to_str_id(value: Any) -> str:
        return "" if value is None else str(value)

    @classmethod
    def _build_item_index(cls, items: List[Dict[str, Any]], *, id_key: str) -> Dict[str, Dict[str, Any]]:
        return {cls._to_str_id(item.get(id_key)): item for item in (items or [])}

    @staticmethod
    def _resolve_source_path(clip: Dict[str, Any], *, media_by_media_id: Mapping[str, Dict[str, Any]]) -> Optional[str]:
        source_ref = clip.get("source_ref") or {}
        media_id = "" if source_ref is None else str(source_ref.get("media_id", ""))
        return media_by_media_id.get(media_id, {}).get("path")

    @staticmethod
    def _safe_float(value: Any, default_value: float = 0.0) -> float:
        try:
            if value is None:
                return default_value
            return float(value)
        except Exception:
            return default_value

    # -----------------------------
    # Beats helpers
    # -----------------------------
    def _build_beat_timestamps_from_music_ms(self, background_music: Dict[str, Any]) -> List[Milliseconds]:
        beats: List[Milliseconds] = background_music.get("beats", []) or []
        music_duration_ms = int(background_music.get("duration", 0))

        if beats:
            if beats[0] != 0:
                return [0] + beats
            return beats

        bpm = background_music.get("bpm")
        if bpm is None:
            return [0]

        bpm_value = self._safe_float(bpm, 0.0)
        if bpm_value <= 0 or music_duration_ms <= 0:
            return [0]

        interval_ms = int(SECONDS_PER_MINUTE / bpm_value * MILLISECONDS_PER_SECOND)

        timestamps_ms: List[Milliseconds] = [0]
        timestamp_ms: Milliseconds = interval_ms
        while timestamp_ms <= music_duration_ms:
            timestamps_ms.append(int(timestamp_ms))
            timestamp_ms += interval_ms

        return timestamps_ms

    @staticmethod
    def _convert_beat_timestamps_to_durations_ms(
        *, beat_timestamps_ms: List[Milliseconds], music_duration_ms: Milliseconds
    ) -> List[Milliseconds]:
        if len(beat_timestamps_ms) < 2:
            return []

        durations_ms: List[Milliseconds] = []
        for start_ms, end_ms in zip(beat_timestamps_ms[:-1], beat_timestamps_ms[1:]):
            delta_ms = int(end_ms) - int(start_ms)
            if delta_ms > 0:
                durations_ms.append(int(delta_ms))

        if music_duration_ms > 0:
            tail_ms = max(0, int(music_duration_ms) - int(beat_timestamps_ms[-1]))
            if tail_ms > 0:
                durations_ms.append(int(tail_ms))

        return durations_ms

    # -----------------------------
    # Text duration estimate
    # -----------------------------
    def _estimate_group_duration_from_text_ms(self, group_script: Optional[Dict[str, Any]]) -> Milliseconds:
        if not group_script:
            return int(self._config.estimate_text_min)

        raw_text = str(group_script.get("raw_text") or "")
        char_count = len(raw_text.strip())
        if char_count <= 0:
            return int(self._config.estimate_text_min)

        chars_per_second = max(1.0, float(self._config.estimate_text_char_per_sec))
        duration_ms = int(char_count / chars_per_second * MILLISECONDS_PER_SECOND)
        return max(int(duration_ms), int(self._config.estimate_text_min))

    # -----------------------------
    # Clip/source windows
    # -----------------------------
    def _full_source_window_and_duration_ms(
        self, clip: Dict[str, Any]
    ) -> Tuple[Milliseconds, Milliseconds, Milliseconds]:
        clip_kind = str(clip.get("kind", "video"))
        source_ref = clip.get("source_ref") or {}

        start_ms = int(source_ref.get("start", 0))
        end_ms = int(source_ref.get("end", start_ms))
        duration_ms = int(source_ref.get("duration", end_ms - start_ms))

        if clip_kind == "image":
            start_ms = 0
            end_ms = int(self._config.image_default_duration)
            duration_ms = end_ms - start_ms
        else:
            if duration_ms <= 0:
                clip_id = clip.get("clip_id")
                raise ValueError(
                    f"{clip_id} has invalid source window (start={start_ms}, end={end_ms}, duration={duration_ms})"
                )

        return int(start_ms), int(end_ms), int(duration_ms)

    def _choose_source_window_for_timeline_duration_ms(
        self, *, clip: Dict[str, Any], used_timeline_duration_ms: Milliseconds
    ) -> Tuple[Milliseconds, Milliseconds]:
        source_start_ms, _, source_duration_ms = self._full_source_window_and_duration_ms(clip)

        random_offset_ms = int(self._random_generator.random() * (source_duration_ms - used_timeline_duration_ms))
        window_start_ms = source_start_ms + random_offset_ms
        window_end_ms = window_start_ms + int(used_timeline_duration_ms)
        return int(window_start_ms), int(window_end_ms)

    # -----------------------------
    # Duration allocation
    # -----------------------------
    def _allocate_clip_durations_using_beats(
        self,
        *,
        clip_items: List[Dict[str, Any]],
        group_target_ms: Milliseconds,
        beat_durations_ms: List[Milliseconds],
        start_beat_index: int,
        start_residual_ms: Milliseconds,
    ) -> Tuple[List[Milliseconds], int]:
        """
        Algorithm (kept the same as legacy version):
        1) Allocate ideal duration per clip by source duration weights (sum to group_target_ms).
        2) Snap each clip end to nearest beat boundary; carry over the delta to next clip.
        3) Last clip snaps to ceil to ensure total >= group_target_ms.
        """
        clip_count = len(clip_items)
        if clip_count == 0:
            return [], int(start_beat_index)

        if not beat_durations_ms:
            raise ValueError("beat_durations is empty")

        weights_ms: List[Milliseconds] = []
        for clip in clip_items:
            _, _, duration_ms = self._full_source_window_and_duration_ms(clip)
            weights_ms.append(int(duration_ms))

        sum_weights = sum(weights_ms)
        targets_ms = [(int(group_target_ms) * w) // sum_weights for w in weights_ms]
        remainder_ms = int(group_target_ms) - sum(targets_ms)

        # Fix integer truncation drift
        fractional_parts = [(i, (int(group_target_ms) * weights_ms[i]) % sum_weights) for i in range(clip_count)]
        fractional_parts.sort(key=lambda x: x[1], reverse=True)
        for k in range(remainder_ms):
            targets_ms[fractional_parts[k][0]] += 1

        # Enforce min clip duration; borrow from longest clips
        deficit_ms: Milliseconds = 0
        for i in range(clip_count):
            if targets_ms[i] < int(self._config.min_clip_duration):
                deficit_ms += int(self._config.min_clip_duration) - targets_ms[i]
                targets_ms[i] = int(self._config.min_clip_duration)

        if deficit_ms > 0:
            indices_by_longest = sorted(range(clip_count), key=lambda i: targets_ms[i], reverse=True)
            for i in indices_by_longest:
                if deficit_ms <= 0:
                    break
                slack_ms = targets_ms[i] - int(self._config.min_clip_duration)
                targets_ms[i] -= slack_ms
                deficit_ms -= slack_ms

        beat_count = len(beat_durations_ms)

        def snap_to_nearest_beat(
            desired_ms: Milliseconds, beat_index: int, phase_ms: Milliseconds
        ) -> Tuple[Milliseconds, int]:
            elapsed_ms = int(phase_ms)
            idx = int(beat_index)

            safety_steps = 0
            while elapsed_ms < int(self._config.min_clip_duration):
                elapsed_ms += int(beat_durations_ms[idx])
                idx = (idx + 1) % beat_count
                safety_steps += 1
                if safety_steps > SNAP_SAFETY_MAX_STEPS:
                    raise RuntimeError("snap_to_nearest_beat safety exceeded")

            if elapsed_ms >= int(desired_ms):
                return int(elapsed_ms), int(idx)

            previous_elapsed_ms = elapsed_ms
            previous_idx = idx

            safety_steps = 0
            while elapsed_ms < int(desired_ms):
                previous_elapsed_ms = elapsed_ms
                previous_idx = idx
                elapsed_ms += int(beat_durations_ms[idx])
                idx = (idx + 1) % beat_count
                safety_steps += 1
                if safety_steps > SNAP_SAFETY_MAX_STEPS:
                    raise RuntimeError("snap_to_nearest_beat safety exceeded")

            if int(desired_ms) - previous_elapsed_ms < elapsed_ms - int(desired_ms):
                return int(previous_elapsed_ms), int(previous_idx)
            return int(elapsed_ms), int(idx)

        def snap_to_beat_ceil(
            desired_ms: Milliseconds, beat_index: int, phase_ms: Milliseconds
        ) -> Tuple[Milliseconds, int]:
            elapsed_ms = int(phase_ms)
            idx = int(beat_index)

            desired_ms = max(int(self._config.min_clip_duration), int(desired_ms))
            safety_steps = 0
            while elapsed_ms < desired_ms:
                elapsed_ms += int(beat_durations_ms[idx])
                idx = (idx + 1) % beat_count
                safety_steps += 1
                if safety_steps > SNAP_SAFETY_MAX_STEPS:
                    raise RuntimeError("snap_to_beat_ceil safety exceeded")
            return int(elapsed_ms), int(idx)

        durations_ms: List[Milliseconds] = []
        beat_index = int(start_beat_index) % beat_count
        phase_ms = max(0, int(start_residual_ms))

        carry_ms: Milliseconds = 0
        sum_actual_ms: Milliseconds = 0

        for i in range(clip_count):
            is_last_clip = i == clip_count - 1

            desired_ms = int(targets_ms[i]) + int(carry_ms)
            if desired_ms < int(self._config.min_clip_duration):
                desired_ms = int(self._config.min_clip_duration)

            if not is_last_clip:
                actual_ms, beat_index = snap_to_nearest_beat(desired_ms, beat_index, phase_ms)
            else:
                remaining_ms = max(0, int(group_target_ms) - int(sum_actual_ms))
                desired_ms = max(desired_ms, int(remaining_ms))
                actual_ms, beat_index = snap_to_beat_ceil(desired_ms, beat_index, phase_ms)

            durations_ms.append(int(actual_ms))
            sum_actual_ms += int(actual_ms)

            carry_ms = desired_ms - int(actual_ms)
            phase_ms = 0  # legacy strategy: always reset

        return durations_ms, int(beat_index)

    def _allocate_clip_durations_without_beats(
        self, *, clip_items: List[Dict[str, Any]], group_target_ms: Milliseconds
    ) -> List[Milliseconds]:
        clip_count = len(clip_items)
        if clip_count == 0:
            return []

        source_durations_ms: List[Milliseconds] = []
        for clip in clip_items:
            _, _, duration_ms = self._full_source_window_and_duration_ms(clip)
            source_durations_ms.append(int(duration_ms))

        total_source_duration_ms = sum(source_durations_ms)

        def total_for_ratio(ratio: float) -> Milliseconds:
            total_ms: Milliseconds = 0
            for duration_ms in source_durations_ms:
                allocated_ms = int(duration_ms * ratio)
                if allocated_ms < int(self._config.min_clip_duration):
                    allocated_ms = int(self._config.min_clip_duration)
                total_ms += int(allocated_ms)
            return int(total_ms)

        ratio_high = max(1.0, int(group_target_ms) / total_source_duration_ms)
        while total_for_ratio(ratio_high) < int(group_target_ms):
            ratio_high *= RATIO_GROWTH_FACTOR
            if ratio_high > RATIO_GROWTH_MAX:
                break

        ratio_low = 0.0
        for _ in range(BINARY_SEARCH_ITERATIONS):
            ratio_mid = (ratio_low + ratio_high) / 2.0
            if total_for_ratio(ratio_mid) <= int(group_target_ms):
                ratio_low = ratio_mid
            else:
                ratio_high = ratio_mid

        ratio = ratio_low

        base_ms: List[Milliseconds] = []
        fractional_parts: List[Tuple[float, int]] = []
        sum_base_ms: Milliseconds = 0

        for i, duration_ms in enumerate(source_durations_ms):
            raw = duration_ms * ratio
            floored = int(raw)

            allocated_ms = floored
            if allocated_ms < int(self._config.min_clip_duration):
                allocated_ms = int(self._config.min_clip_duration)
                fraction = -1.0
            else:
                fraction = raw - floored

            base_ms.append(int(allocated_ms))
            sum_base_ms += int(allocated_ms)
            fractional_parts.append((float(fraction), i))

        remaining_ms: Milliseconds = int(group_target_ms) - int(sum_base_ms)
        if remaining_ms > 0:
            fractional_parts.sort(key=lambda x: (x[0], source_durations_ms[x[1]]), reverse=True)
            j = 0
            # NOTE: matches legacy behavior (no wrap-around); remaining_ms too large may raise IndexError.
            while remaining_ms > 0:
                idx = fractional_parts[j][1]
                base_ms[idx] += 1
                remaining_ms -= 1
                j += 1

        return base_ms


@NODE_REGISTRY.register()
class PlanTimelineNode(BaseNode):
    meta = NodeMeta(
        name="plan_timeline",
        description=(
            "Create a coherent timeline by arranging video clips, subtitles, voice-over, and background music. "
            "Required: load_media. Optional: generate_script, detect_highlights, select_BGM, generate_voiceover"
        ),
        node_id="plan_timeline",
        node_kind="plan_timeline",
        require_prior_kind=["load_media", "split_shots", "group_clips", "generate_script", "tts", "music_rec"],
        default_require_prior_kind=["load_media", "split_shots", "group_clips", "generate_script", "tts", "music_rec"],
        next_available_node=["render_video"],
    )

    input_schema = PlanTimelineInput

    def __init__(self, server_cfg: Settings) -> None:
        super().__init__(server_cfg)
        config: PlanTimelineConfig = self.server_cfg.plan_timeline
        self.planner = TimelinePlanner(config, random_seed=DEFAULT_RANDOM_SEED)


    async def default_process(self, node_state: NodeState, inputs: Dict[str, Any]) -> Any:
        return await self.process(node_state, inputs)

    async def process(self, node_state, inputs: Dict[str, Any]) -> Dict[str, Any]:
        # Inputs (defensive parsing for open-source robustness)
        media = (inputs.get("load_media") or {}).get("media", [])
        clips = (inputs.get("split_shots") or {}).get("clips", [])
        groups = (inputs.get("group_clips") or {}).get("groups", [])
        group_scripts = (inputs.get("generate_script") or {}).get("group_scripts", [])
        voiceovers = (inputs.get("tts") or {}).get("voiceover", [])
        background_music = (inputs.get("music_rec") or {}).get("bgm")  # Optional dict
        use_beats = inputs.get("use_beats", False)

        result = self.planner.plan(
            media=media,
            clips=clips,
            groups=groups,
            group_scripts=group_scripts,
            voiceovers=voiceovers,
            background_music=background_music,
            use_beats=use_beats,
        )

        node_state.node_summary.info_for_user("时间线组织成功")
        return result
