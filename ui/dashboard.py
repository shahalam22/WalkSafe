"""
WalkSafe Research Dashboard
Run standalone: python -m ui.dashboard
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import gradio as gr
import pandas as pd

from storage import queries

_RISK_COLORS = {
    "critical": "#e74c3c",
    "high":     "#e67e22",
    "moderate": "#f1c40f",
    "low":      "#2ecc71",
}
_CMD_COLOR = "#4a90d9"
_ACT_COLOR = "#7b68ee"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _bar(df, x_col, y_col, title, color, rotate=True):
    fig, ax = plt.subplots(figsize=(7, 3.5))
    if df.empty:
        ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
    else:
        ax.bar(df[x_col], df[y_col], color=color)
        if rotate:
            plt.xticks(rotation=35, ha="right", fontsize=9)
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.set_ylabel("Count")
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()
    return fig


def _line(df, title):
    fig, ax = plt.subplots(figsize=(10, 3))
    if df.empty:
        ax.text(0.5, 0.5, "No data — select a session", ha="center", va="center",
                transform=ax.transAxes)
    else:
        ax.plot(df["frame_idx"], df["ego_speed_ms"], linewidth=1.2, color="#4a90d9")
        ax.fill_between(df["frame_idx"], df["ego_speed_ms"], alpha=0.15, color="#4a90d9")
        ax.set_xlabel("Frame")
        ax.set_ylabel("Speed (m/s)")
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()
    return fig


# ── Callbacks ─────────────────────────────────────────────────────────────────

def refresh():
    df      = queries.get_sessions()
    choices = ["All sessions"] + df["session_id"].tolist() if not df.empty else ["All sessions"]
    return df, gr.Dropdown(choices=choices, value="All sessions")


def update(session_choice):
    sid = None if (not session_choice or session_choice == "All sessions") else session_choice

    summary = queries.get_summary(sid)
    s_frames  = str(summary["total_frames"])
    s_speed   = f"{summary['avg_speed_ms']:.2f} m/s"
    s_agents  = str(summary["total_agents"])
    s_critical = str(summary["critical_count"])

    cmd_fig  = _bar(queries.get_command_distribution(sid), "command",    "count",
                    "Navigation Commands", _CMD_COLOR)
    risk_fig = _bar(queries.get_risk_distribution(sid),   "risk_level", "count",
                    "Agent Risk Levels",
                    [_RISK_COLORS.get(r, "#aaa") for r in queries.get_risk_distribution(sid)["risk_level"]],
                    rotate=False)
    act_fig  = _bar(queries.get_action_distribution(sid), "action",     "count",
                    "User Actions",       _ACT_COLOR)
    spd_fig  = _line(
        queries.get_speed_over_time(sid) if sid else pd.DataFrame(),
        "Speed Profile" + (f"  ·  session {sid[:8]}" if sid else " (select a session)"),
    )

    return s_frames, s_speed, s_agents, s_critical, cmd_fig, risk_fig, act_fig, spd_fig


# ── Layout ────────────────────────────────────────────────────────────────────

def build_dashboard():
    with gr.Blocks(title="WalkSafe Dashboard", theme=gr.themes.Default()) as demo:
        gr.Markdown("# WalkSafe — Research Dashboard")

        with gr.Row():
            refresh_btn = gr.Button("Refresh", variant="secondary", scale=0)
            session_dd  = gr.Dropdown(
                label="Session", choices=["All sessions"], value="All sessions", scale=2
            )

        # Sessions table
        sessions_table = gr.Dataframe(
            label="Sessions",
            headers=["session_id", "started", "duration_min", "total_frames"],
            interactive=False,
        )

        # Summary cards
        with gr.Row():
            m_frames   = gr.Textbox(label="Total Frames",    interactive=False)
            m_speed    = gr.Textbox(label="Avg Speed",       interactive=False)
            m_agents   = gr.Textbox(label="Agent Encounters",interactive=False)
            m_critical = gr.Textbox(label="Critical Events", interactive=False)

        # Charts — row 1
        with gr.Row():
            cmd_plot  = gr.Plot(label="Navigation Commands")
            risk_plot = gr.Plot(label="Agent Risk Levels")

        # Charts — row 2
        with gr.Row():
            act_plot = gr.Plot(label="User Actions")

        # Speed profile — full width
        spd_plot = gr.Plot(label="Speed Profile")

        # ── Wiring ────────────────────────────────────────────────────────────
        chart_outputs = [m_frames, m_speed, m_agents, m_critical,
                         cmd_plot, risk_plot, act_plot, spd_plot]

        refresh_btn.click(fn=refresh, outputs=[sessions_table, session_dd])
        session_dd.change(fn=update, inputs=[session_dd], outputs=chart_outputs)
        demo.load(fn=refresh, outputs=[sessions_table, session_dd])

    return demo


if __name__ == "__main__":
    build_dashboard().launch()
