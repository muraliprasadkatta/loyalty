from __future__ import annotations

from typing import Any, Dict, List, Optional


def _suffix(n: int) -> str:
    """1st/2nd/3rd/4th..."""
    if 10 <= (n % 100) <= 20:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def _to_int_list(xs) -> List[int]:
    out: List[int] = []
    if not xs:
        return out
    for v in xs:
        try:
            n = int(v)
        except (TypeError, ValueError):
            continue
        if n > 0:
            out.append(n)
    return sorted(set(out))


def offers_progress_modal_context(
    *,
    total_visits: int,
    nth: Optional[int],
    repeat: bool,
    extra_nths: Optional[List[int]] = None,
    max_preview: int = 15,
    include_repeat_multiples: bool = True,
    progress_span_mode: str = "max",
) -> Dict[str, Any]:
    """
    Build UI-ready context for offers_progress_modal.

    Behavior:
    - milestones takkuva unte fit-mode: visible width lo spread avvali
    - milestones ekkuva unte scroll-mode: pixel-gap based track peragali
    - fill smooth ga interpolate avvali
    """

    try:
        total_visits_i = int(total_visits or 0)
    except Exception:
        total_visits_i = 0
    if total_visits_i < 0:
        total_visits_i = 0

    nth_i: Optional[int] = None
    if nth is not None and str(nth).strip() != "":
        try:
            nth_i = int(nth)
        except (TypeError, ValueError):
            nth_i = None
    if nth_i is not None and nth_i <= 0:
        nth_i = None

    try:
        mp = int(max_preview or 0)
    except Exception:
        mp = 0
    if mp < 0:
        mp = 0

    extra = _to_int_list(extra_nths)
    has_milestones = bool(nth_i or extra)

    if not has_milestones:
        return {
            "has_milestones": False,
            "points_label": f"{total_visits_i}+",
            "nth": 0,
            "repeat": bool(repeat),
            "extra_nths": [],
            "current_progress": 0,
            "progress_total": 0,
            "progress_pct": 0,
            "preview_boxes": [],
            "rows": [],
            "milestones": [],
            "track_width_px": 360,
            "fill_width_px": 10,
            "fill_width_pct": None,
            "start_marker_px": 46,
            "start_marker_pct": None,
            "first_milestone_px": 96,
            "track_end_px": 36,
            "track_gap_px": 88,
            "fit_mode": True,
        }

    milestone_visits: List[int] = []

    if nth_i:
        milestone_visits.append(nth_i)

        if repeat and include_repeat_multiples and mp > 0:
            k = 2
            while (nth_i * k) <= mp:
                milestone_visits.append(nth_i * k)
                k += 1

    milestone_visits.extend(extra)
    milestone_visits = sorted(set(v for v in milestone_visits if v > 0))

    if not milestone_visits:
        return {
            "has_milestones": False,
            "points_label": f"{total_visits_i}+",
            "nth": nth_i or 0,
            "repeat": bool(repeat),
            "extra_nths": extra,
            "current_progress": 0,
            "progress_total": 0,
            "progress_pct": 0,
            "preview_boxes": [],
            "rows": [],
            "milestones": [],
            "track_width_px": 360,
            "fill_width_px": 10,
            "fill_width_pct": None,
            "start_marker_px": 46,
            "start_marker_pct": None,
            "first_milestone_px": 96,
            "track_end_px": 36,
            "track_gap_px": 88,
            "fit_mode": True,
        }

    upcoming = [v for v in milestone_visits if v > total_visits_i]
    active_target = min(upcoming) if upcoming else None

    def state_for(v: int) -> str:
        if total_visits_i >= v:
            return "done"
        if active_target is not None and v == active_target:
            return "active"
        return "lock"

    def icon_for(v: int, is_main: bool) -> str:
        st = state_for(v)
        if st == "done":
            return "✓"
        if st == "active":
            return "⭐" if is_main else "🎯"
        return "🔒"

    current_progress = 0
    progress_total = 0
    progress_pct = 0

    if nth_i and progress_span_mode == "nth":
        progress_total = nth_i
        if repeat:
            current_progress = (total_visits_i % nth_i) or (nth_i if total_visits_i else 0)
        else:
            current_progress = min(total_visits_i, nth_i)
        progress_pct = int(round((current_progress / progress_total) * 100)) if progress_total else 0
    else:
        progress_total = max(milestone_visits) if milestone_visits else (nth_i or 0)
        if progress_total:
            current_progress = min(total_visits_i, progress_total)
            progress_pct = int(round((current_progress / progress_total) * 100))
        else:
            current_progress = 0
            progress_pct = 0

    rows: List[Dict[str, Any]] = []
    for v in milestone_visits:
        is_reward_milestone = bool(nth_i and v == nth_i)
        is_main = bool(active_target is not None and v == active_target)

        rows.append(
            {
                "visit_no": v,
                "label": f"{v}{_suffix(v)} visit",
                "state": state_for(v),
                "is_main": is_main,
                "is_reward_milestone": is_reward_milestone,
                "icon": icon_for(v, is_main),
                "title": "Free Treat" if is_reward_milestone else "Extra Treat!",
                "date_label": "",
            }
        )

    milestone_count = len(milestone_visits)

    start_marker_px = 46
    first_milestone_px = 96
    track_end_px = 24
    track_gap_px = 88

    fit_mode = milestone_count <= 4

    base_fit_track_width_px = 360
    start_marker_pct = None
    fill_width_pct = None

    if fit_mode:
        track_width_px = base_fit_track_width_px
        usable_start = first_milestone_px
        usable_end = track_width_px - track_end_px

        start_marker_pct = round((start_marker_px / track_width_px) * 100, 4)
        usable_start_pct = (usable_start / track_width_px) * 100
        usable_end_pct = (usable_end / track_width_px) * 100

        def milestone_x(index: int) -> int:
            if milestone_count <= 1:
                return usable_end
            span = usable_end - usable_start
            step = span / (milestone_count - 1)
            return int(round(usable_start + (index * step)))

        def milestone_left_pct(index: int) -> float:
            if milestone_count <= 1:
                return round(usable_end_pct, 4)
            span = usable_end_pct - usable_start_pct
            step = span / (milestone_count - 1)
            return round(usable_start_pct + (index * step), 4)

    else:
        if milestone_count <= 2:
            track_gap_px = 92
        elif milestone_count >= 8:
            track_gap_px = 84

        track_width_px = first_milestone_px + track_end_px + max(0, (milestone_count - 1) * track_gap_px)
        track_width_px = max(360, track_width_px)

        def milestone_x(index: int) -> int:
            return first_milestone_px + (index * track_gap_px)

        def milestone_left_pct(index: int) -> Optional[float]:
            return None

    def fill_x_for_visits(visits_done: int) -> int:
        if not milestone_visits:
            return start_marker_px + 8

        if visits_done <= 0:
            return start_marker_px + 8

        first_target = milestone_visits[0]
        first_x = milestone_x(0)

        if visits_done < first_target:
            ratio = visits_done / first_target if first_target > 0 else 0
            return int(round(start_marker_px + ((first_x - start_marker_px) * ratio)))

        prev_visit = 0
        prev_x = start_marker_px

        for idx, target_visit in enumerate(milestone_visits):
            target_x = milestone_x(idx)

            if visits_done == target_visit:
                return target_x

            if visits_done < target_visit:
                span_visits = target_visit - prev_visit
                if span_visits <= 0:
                    return target_x
                ratio = (visits_done - prev_visit) / span_visits
                return int(round(prev_x + ((target_x - prev_x) * ratio)))

            prev_visit = target_visit
            prev_x = target_x

        return milestone_x(len(milestone_visits) - 1)

    fill_width_px = fill_x_for_visits(total_visits_i)
    fill_width_px = max(10, min(track_width_px - 8, fill_width_px))

    if fit_mode:
        fill_width_pct = round((fill_width_px / track_width_px) * 100, 4)

    milestones: List[Dict[str, Any]] = []
    for idx, v in enumerate(milestone_visits):
        is_reward_milestone = bool(nth_i and v == nth_i)
        is_main = bool(active_target is not None and v == active_target)

        milestones.append(
            {
                "visit_no": v,
                "label": f"{v}{_suffix(v)}",
                "left_px": milestone_x(idx),
                "left_pct": milestone_left_pct(idx),
                "state": state_for(v),
                "is_main": is_main,
                "is_reward_milestone": is_reward_milestone,
            }
        )

    preview_boxes: List[Dict[str, Any]] = []
    for v in range(1, mp + 1):
        kind = "normal"

        if nth_i and v == nth_i:
            kind = "main"
        elif v in extra:
            kind = "extra"

        if nth_i and (not repeat) and v > nth_i:
            kind = "locked"

        if v in milestone_visits:
            st = state_for(v)
        else:
            st = "done" if total_visits_i >= v else "normal"

        preview_boxes.append(
            {
                "visit_no": v,
                "kind": kind,
                "state": st,
            }
        )

    return {
        "has_milestones": True,
        "points_label": f"{total_visits_i}+",
        "nth": nth_i or 0,
        "repeat": bool(repeat),
        "extra_nths": extra,
        "current_progress": current_progress,
        "progress_total": progress_total,
        "progress_pct": progress_pct,
        "preview_boxes": preview_boxes,
        "rows": rows,
        "milestones": milestones,
        "track_width_px": track_width_px,
        "fill_width_px": fill_width_px,
        "fill_width_pct": fill_width_pct,
        "start_marker_px": start_marker_px,
        "start_marker_pct": start_marker_pct,
        "first_milestone_px": first_milestone_px,
        "track_end_px": track_end_px,
        "track_gap_px": track_gap_px,
        "fit_mode": fit_mode,
    }