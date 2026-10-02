"""Research dashboard (FR-26): summaries, guidance delay against target, time at
each capability level, and drill-down from any decision to the agents and
openings behind it. Mounted at /dashboard behind a login."""
import base64

import matplotlib

matplotlib.use("Agg")
import gradio as gr  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from walksafe.config import CFG, Config  # noqa: E402
from walksafe.storage import queries  # noqa: E402

RISK_COLORS = {"critical": "#e74c3c", "high": "#e67e22", "moderate": "#f1c40f", "low": "#2ecc71"}
LEVEL_COLORS = {"L0": "#2ecc71", "L1": "#f1c40f", "L2": "#e67e22", "L3": "#e74c3c", "L4": "#7f8c8d"}
BAR_COLOR = "#4a90d9"
ALL = "All sessions"


def _figure(title, empty, draw, size=(7, 3.5)):
    fig, ax = plt.subplots(figsize=size)
    if empty:
        ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
    else:
        draw(ax)
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()
    plt.close(fig)
    return fig


def _bars(df, x, title, colors=None):
    def draw(ax):
        ax.bar(df[x], df[df.columns[1]], color=colors or BAR_COLOR)
        ax.tick_params(axis="x", labelrotation=30)
    return _figure(title, df.empty, draw)


def _delays(df, target_ms):
    def draw(ax):
        ax.hist(df["delay_ms"], bins=30, color=BAR_COLOR)
        ax.axvline(target_ms, color="#e74c3c", linestyle="--", label=f"target {target_ms} ms")
        ax.set_xlabel("capture to speech (ms)")
        ax.legend()
    return _figure("Guidance delay", df.empty, draw)


def _speed(df):
    def draw(ax):
        ax.plot(df["t_s"], df["user_speed_ms"], linewidth=1.2, color=BAR_COLOR)
        ax.set_xlabel("time (s)")
        ax.set_ylabel("walking speed (m/s)")
    return _figure("Walking speed", df.empty, draw, size=(10, 3))


def build_dashboard(db_path: str = CFG.storage.db_path, sessions=None, cfg: Config = CFG) -> gr.Blocks:
    """sessions is the server's SessionStore, needed only for the live view."""
    target = cfg.ui.delay_target_ms

    def refresh():
        df = queries.sessions(db_path)
        return df, gr.Dropdown(choices=[ALL] + df["session_id"].tolist(), value=ALL)

    def update(choice):
        sid = None if choice in (None, ALL) else choice
        s = queries.summary(db_path, sid, target)
        risks = queries.counts(db_path, "agent", "risk", sid)
        levels = queries.level_time(db_path, sid)
        decisions = queries.decision_list(db_path, sid) if sid else pd.DataFrame()
        labels = [f"{r.source} #{r.sequence} {r.command}" for r in decisions.itertuples()]
        return (
            f"{s['decisions']} server, {s['phone_stops']} phone stops",
            f"{s['avg_speed']:.2f} m/s",
            f"{s['agents']} tracked, {s['critical']} critical sightings",
            "no spoken guidance yet" if s["on_time_pct"] is None else f"{s['on_time_pct']} % within {target} ms",
            _bars(queries.counts(db_path, "decision", "command", sid), "command", "Commands"),
            _bars(risks, "risk", "Agent risk", [RISK_COLORS.get(r, "#aaa") for r in risks["risk"]]),
            _delays(queries.delays(db_path, sid), target),
            _bars(levels, "level", "Time at each level (s)", [LEVEL_COLORS.get(v, "#aaa") for v in levels["level"]]),
            _speed(queries.speed_over_time(db_path, sid) if sid else pd.DataFrame()),
            gr.Dropdown(choices=labels, value=None),
        )

    def drill(choice, label):
        if not label or choice in (None, ALL):
            return "", pd.DataFrame(), pd.DataFrame()
        source, seq = label.split()[0], int(label.split()[1][1:])
        row, agents, openings = queries.decision_detail(db_path, choice, source, seq)
        text = "" if row is None else (
            f"**{row['command']}** ({row['source']} #{row['sequence']}, level {row['level']}, "
            f"confidence {row['confidence']}, spoken {bool(row['spoken'])}, delay {row['delay_ms']} ms)\n\n"
            f"Detail: {row['detail']}\n\nReason: `{row['reason']}`")
        return text, agents, openings

    with gr.Blocks(title="WalkSafe Dashboard") as demo:
        gr.Markdown("# WalkSafe research dashboard")
        with gr.Row():
            refresh_btn = gr.Button("Refresh", variant="secondary", scale=0)
            session_dd = gr.Dropdown(label="Session", choices=[ALL], value=ALL, scale=2)
        table = gr.Dataframe(label="Sessions", interactive=False)

        with gr.Row():
            m_decisions = gr.Textbox(label="Decisions", interactive=False)
            m_speed = gr.Textbox(label="Average walking speed", interactive=False)
            m_agents = gr.Textbox(label="Agents", interactive=False)
            m_delay = gr.Textbox(label="Guidance on time (NFR-2)", interactive=False)
        with gr.Row():
            cmd_plot, risk_plot = gr.Plot(label="Commands"), gr.Plot(label="Agent risk")
        with gr.Row():
            delay_plot, level_plot = gr.Plot(label="Guidance delay"), gr.Plot(label="Time at each level")
        speed_plot = gr.Plot(label="Walking speed")

        gr.Markdown("## Drill-down")
        decision_dd = gr.Dropdown(label="Decision", choices=[])
        detail = gr.Markdown()
        with gr.Row():
            agents_df = gr.Dataframe(label="Agents", interactive=False)
            openings_df = gr.Dataframe(label="Openings", interactive=False)

        outputs = [m_decisions, m_speed, m_agents, m_delay, cmd_plot, risk_plot,
                   delay_plot, level_plot, speed_plot, decision_dd]
        refresh_btn.click(refresh, outputs=[table, session_dd])
        session_dd.change(update, inputs=[session_dd], outputs=outputs)
        decision_dd.change(drill, inputs=[session_dd, decision_dd], outputs=[detail, agents_df, openings_df])
        demo.load(refresh, outputs=[table, session_dd])

        with gr.Tab("Live view"):
            if cfg.ui.diagnostic_view and sessions is not None:
                live = gr.HTML()
                gr.Timer(1.0).tick(lambda: _live_panel(sessions), outputs=live)
            else:
                gr.Markdown("The live fusion panel is off. Set `ui.diagnostic_view: true` to turn it on.")
    return demo


def _live_panel(sessions) -> str:
    # Sent inline: a gr.Image would be written to Gradio's cache on disk.
    panels = [s.panel for s in sessions.all() if s.panel]
    if not panels:
        return "<p>No live session.</p>"
    return f'<img alt="Fusion panel" style="max-width:100%" src="data:image/jpeg;base64,{base64.b64encode(panels[-1]).decode()}">'
