"""Agent-flow views: green-light agent cards, live LangGraph chart, models panel, timeline, map.

Everything here renders safe, already-sanitised run data (static event summaries and the
validated plan). Nothing reads prompts, credentials or raw provider responses.
"""

import streamlit as st

# (card label, graph task id, role key used by agent summaries)
AGENTS = (
    ("Orchestrator", "parse", "orchestrator"),
    ("Destination research", "destination", "destination"),
    ("Logistics", "preliminary", "logistics"),
    ("Planner", "planner", "planner"),
    ("Scheduler", "scheduler", "scheduler"),
    ("Budget", "costing", "budget"),
    ("Review", "review", "reviewer"),
)
LIGHTS = {"done": "🟢", "running": "🟡", "waiting": "⚪", "stopped": "🔴"}
NODE_STYLE = {
    "done": ("#c9f2d4", "#2e9e5b"),
    "running": ("#fff1b8", "#d9a400"),
    "waiting": ("#f1f1f1", "#9a9a9a"),
    "stopped": ("#ffd6d6", "#c0392b"),
}
DAY_COLORS = ["#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#008080", "#9a6324"]


def task_status(events, task, *, finished=False, failed=False):
    """done / running / waiting / stopped for one graph task, from static event kinds."""
    related = [event for event in events if event.task_id == task]
    if any(event.kind == "artifact_ready" for event in related):
        return "done"
    if any(event.kind == "agent_started" for event in related):
        return "stopped" if (finished and failed) else "running"
    return "waiting"


def _summary_for(role, summaries):
    prefix = role + "/"
    matches = [line for line in summaries if line.startswith(prefix)]
    return matches[-1].split(": ", 1)[-1] if matches else None


def agent_cards(events, summaries=(), *, finished=False, failed=False):
    """Two-column grid of agent cards with a status light, summary and event list."""
    columns = st.columns(2)
    for index, (label, task, role) in enumerate(AGENTS):
        status = task_status(events, task, finished=finished, failed=failed)
        related = [event for event in events if event.task_id == task]
        with columns[index % 2].container(border=True):
            st.markdown(f"{LIGHTS[status]} **{label}** — {status}")
            summary = _summary_for(role, summaries)
            if summary:
                st.caption(summary)
            elif status == "running":
                st.caption("Working…")
            elif status == "waiting":
                st.caption("Waiting for earlier agents.")
            with st.expander(f"{len(related)} event(s)"):
                if not related:
                    st.caption("No events yet.")
                for event in related:
                    st.caption(
                        f"#{event.sequence} · {event.kind.replace('_', ' ')} · {event.summary}"
                    )


def graph_dot(events, *, finished=False, failed=False):
    """Graphviz DOT for the LangGraph wiring, with nodes coloured by live status."""
    state = {
        task: task_status(events, task, finished=finished, failed=failed)
        for task in (
            "parse",
            "research",
            "destination",
            "preliminary",
            "planner",
            "scheduler",
            "costing",
            "review",
            "decide",
            "repair",
            "finish",
        )
    }
    names = {task: label for label, task, _ in AGENTS}
    lines = [
        "digraph G {",
        "rankdir=TB;",
        'graph [bgcolor="transparent", nodesep=0.35, ranksep=0.35];',
        'node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=11, penwidth=1.5];',
        'edge [color="#666666", arrowsize=0.7];',
        '"__start__" [shape=ellipse, fillcolor="#f1f1f1", color="#9a9a9a", label="start"];',
        '"__end__" [shape=ellipse, fillcolor="#f1f1f1", color="#9a9a9a", label="end"];',
    ]
    for task, status in state.items():
        fill, border = NODE_STYLE[status]
        caption = task if task not in names else f"{task}\\n({names[task]})"
        lines.append(f'"{task}" [fillcolor="{fill}", color="{border}", label="{caption}"];')
    edges = [
        ("__start__", "parse", ""),
        ("parse", "research", ""),
        ("parse", "finish", 'style=dotted, label="needs input"'),
        ("research", "destination", ""),
        ("research", "preliminary", ""),
        ("destination", "planner", ""),
        ("preliminary", "planner", ""),
        ("planner", "scheduler", ""),
        ("scheduler", "costing", ""),
        ("costing", "review", ""),
        ("review", "decide", ""),
        ("decide", "repair", 'style=dotted, label="revise"'),
        ("repair", "planner", "style=dashed"),
        ("decide", "finish", 'style=dotted, label="pass"'),
        ("finish", "__end__", ""),
    ]
    for source, target, attrs in edges:
        lines.append(f'"{source}" -> "{target}"' + (f" [{attrs}];" if attrs else ";"))
    lines.append("}")
    return "\n".join(lines)


def agent_graph(events, *, finished=False, failed=False):
    st.graphviz_chart(graph_dot(events, finished=finished, failed=failed))
    st.caption("Green done · yellow running · grey waiting · red stopped. Dotted = conditional.")


def agent_models_panel(settings):
    """Sidebar panel: which provider and model each agent talks to."""
    ready = settings.capabilities["model_runner"]
    rows = [
        (label, "groq", settings.groq_model) for label, _, role in AGENTS if role != "reviewer"
    ] + [("Review", "gemini", settings.gemini_model)]
    with st.sidebar.expander("Agent models", expanded=True):
        for label, provider, model in rows:
            st.markdown(f"{'🟢' if ready else '⚪'} **{label.lower()}** · {provider}")
            st.caption(model)
        if not ready:
            st.caption("Add both private API keys to enable the AI agents.")
        st.caption(f"Max revisions: {settings.max_revisions} · Data mode: local")


def _price_text(prices):
    usable = [p for p in prices if p.status != "unknown" and p.low is not None]
    if not usable:
        return "—", "unknown"
    price = usable[0]
    amount = (
        "free"
        if price.high == 0
        else (f"{price.low:g}" if price.low == price.high else f"{price.low:g}–{price.high:g}")
    )
    return amount, price.status


def _minutes(window):
    if window.kind == "dated":
        return int((window.end - window.start).total_seconds() // 60), window.start.strftime(
            "%H:%M"
        )
    return window.end_minute - window.start_minute, (
        f"{window.start_minute // 60:02d}:{window.start_minute % 60:02d}"
    )


def timeline_rows(result, catalog):
    """Chronological per-day rows: stops and the legs between them, with AED and a status."""
    names = {}
    prices = {}
    if catalog is not None:
        names = {r.id: r.name for r in [*catalog.places, *catalog.accommodation]}
        for price in catalog.prices:
            prices.setdefault(price.entity_id, []).append(price)
            prices.setdefault(price.id, []).append(price)

    def name(record_id):
        return names.get(record_id, record_id.replace("-", " ").title())

    rows = []
    for day in result.days:
        legs = list(day.routes)
        for index, activity in enumerate(day.activities):
            if index < len(legs):
                leg = legs[index]
                cost, _ = _price_text(prices.get(leg.price_id, [])) if leg.price_id else ("—", "")
                rows.append(
                    {
                        "Day": day.day,
                        "Time": "",
                        "Activity": f"🚕 {leg.mode.title()}: {name(leg.origin_id)} → {name(leg.destination_id)}",
                        "Minutes": f"{leg.duration_min}–{leg.duration_max}"
                        if leg.duration_min is not None
                        else "to confirm",
                        "AED / person": cost,
                        "Status": "≈ estimated",
                    }
                )
            minutes, start = _minutes(activity.window)
            amount, price_status = _price_text(prices.get(activity.place_id, []))
            verified = price_status == "known" and activity.hours_check == "checked"
            rows.append(
                {
                    "Day": day.day,
                    "Time": start,
                    "Activity": f"📍 {name(activity.place_id)}",
                    "Minutes": str(minutes),
                    "AED / person": amount,
                    "Status": "✅ verified" if verified else "≈ estimated",
                }
            )
        if len(legs) > len(day.activities):
            leg = legs[-1]
            cost, _ = _price_text(prices.get(leg.price_id, [])) if leg.price_id else ("—", "")
            rows.append(
                {
                    "Day": day.day,
                    "Time": "",
                    "Activity": f"🚕 {leg.mode.title()}: {name(leg.origin_id)} → {name(leg.destination_id)}",
                    "Minutes": f"{leg.duration_min}–{leg.duration_max}"
                    if leg.duration_min is not None
                    else "to confirm",
                    "AED / person": cost,
                    "Status": "≈ estimated",
                }
            )
    return rows


def map_points(result, catalog):
    """Stops (coloured by day) and the hotel area as lat/lon rows for st.map."""
    if catalog is None:
        return []
    places = {p.id: p for p in catalog.places}
    points = []
    if result.accommodation:
        area = places.get(result.accommodation[0].area_id)
        if area is not None and area.coordinates is not None:
            points.append(
                {
                    "lat": area.coordinates.latitude,
                    "lon": area.coordinates.longitude,
                    "color": "#555555",
                    "size": 260,
                }
            )
    for day in result.days:
        color = DAY_COLORS[(day.day - 1) % len(DAY_COLORS)]
        for activity in day.activities:
            place = places.get(activity.place_id)
            if place is not None and place.coordinates is not None:
                points.append(
                    {
                        "lat": place.coordinates.latitude,
                        "lon": place.coordinates.longitude,
                        "color": color,
                        "size": 180,
                    }
                )
    return points


def show_timeline_and_map(result, catalog):
    rows = timeline_rows(result, catalog)
    if rows:
        st.markdown("**Day-by-day timeline**")
        st.dataframe(rows, hide_index=True, width="stretch")
        st.caption(
            "AED is per traveler. Verified = published price and checked hours; estimated = "
            "planning allowance or heuristic. Taxi times are road-network estimates."
        )
    points = map_points(result, catalog)
    if points:
        st.markdown("**Map**")
        st.map(points, latitude="lat", longitude="lon", color="color", size="size")
        legend = " · ".join(
            f"<span style='color:{DAY_COLORS[(d.day - 1) % len(DAY_COLORS)]}'>●</span> Day {d.day}"
            for d in result.days
        )
        st.markdown(f"<small>Grey ● hotel area · {legend}</small>", unsafe_allow_html=True)
        st.caption(
            "Pins use approximate catalog coordinates, not exact entrances. Map tiles are "
            "supplied by Streamlit's default map provider (OpenStreetMap contributors)."
        )
