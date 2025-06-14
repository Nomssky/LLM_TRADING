import streamlit as st
import pandas as pd
import json
from datetime import datetime, timedelta
import altair as alt
from streamlit_autorefresh import st_autorefresh
import streamlit.components.v1 as components

# --- KONFIGURASI UTAMA ---
JSON_FILE = "sinyal_trading.json"
PNL_MULTIPLIER = 0.01 

# Warna kustom
COLOR_PROFIT = '#2ecc71'
COLOR_LOSS = '#e74c3c'
COLOR_OTHER = '#f39c12'
COLOR_LINE = '#3498db'
COLOR_PENDING = '#3498db'

# --- FUNGSI-FUNGSI BANTUAN ---

def load_css():
    st.markdown("""
        <style>
        .main .block-container { padding: 2rem !important; }
        h1, h3 { margin-top: 0 !important; padding-top: 0 !important; }
        .metric-container { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 1rem; }
        .metric-card { background-color: #2a2a2a; border-radius: 8px; padding: 1rem; text-align: center; }
        .metric-label { font-size: 0.9rem; color: #a0a0a0; margin-bottom: 0.5rem; }
        .metric-value { font-size: 1.5rem; font-weight: bold; }
        </style>""", unsafe_allow_html=True)

def load_signals():
    try:
        df = pd.read_json(JSON_FILE)
        if df.empty: return pd.DataFrame()
        df['Waktu'] = pd.to_datetime(df['Waktu'], errors='coerce')
        df.dropna(subset=['Waktu'], inplace=True)
        return df.sort_values('Waktu', ascending=False)
    except Exception as e:
        st.error(f"Gagal memuat {JSON_FILE}: {e}")
        return pd.DataFrame()

def calculate_pnl(row):
    try:
        entry, sl, tp = float(row['Entry']), float(row['SL']), float(row['TP'])
        tipe, hasil = str(row.get('Tipe', '')).upper(), str(row.get('Hasil', '')).upper()
        if hasil == "TP": pnl = abs(tp - entry) * PNL_MULTIPLIER
        elif hasil == "SL": pnl = -abs(sl - entry) * PNL_MULTIPLIER
        else: pnl = 0.0
        return pnl
    except (ValueError, TypeError): return 0.0

def render_holistic_summary(metrics):
    st.markdown("### Ringkasan Performa Holistik")
    c1, c2 = st.columns([3, 1])
    with c1:
        st.markdown('<div class="metric-container">', unsafe_allow_html=True)
        m_cols = st.columns(4)
        m_cols[0].markdown(f"""<div class="metric-card"><div class="metric-label">Total PnL</div><div class="metric-value" style="color: {'{COLOR_PROFIT}' if metrics['total_pnl'] >= 0 else '{COLOR_LOSS}'};">${metrics['total_pnl']:,.2f}</div></div>""", unsafe_allow_html=True)
        m_cols[1].markdown(f"""<div class="metric-card"><div class="metric-label">Win Rate (dari dieksekusi)</div><div class="metric-value">{metrics['win_rate']:.1f}%</div></div>""", unsafe_allow_html=True)
        m_cols[2].markdown(f"""<div class="metric-card"><div class="metric-label">Total Sinyal</div><div class="metric-value">{metrics['total_signals']}</div></div>""", unsafe_allow_html=True)
        m_cols[3].markdown(f"""<div class="metric-card"><div class="metric-label">Eksekusi Rate</div><div class="metric-value">{metrics['execution_rate']:.1f}%</div></div>""", unsafe_allow_html=True)
        m_cols = st.columns(4)
        m_cols[0].markdown(f"""<div class="metric-card"><div class="metric-label">Total Wins</div><div class="metric-value" style="color: {COLOR_PROFIT};">{metrics['total_win']}</div></div>""", unsafe_allow_html=True)
        m_cols[1].markdown(f"""<div class="metric-card"><div class="metric-label">Total Losses</div><div class="metric-value" style="color: {COLOR_LOSS};">{metrics['total_loss']}</div></div>""", unsafe_allow_html=True)
        m_cols[2].markdown(f"""<div class="metric-card"><div class="metric-label">Invalid</div><div class="metric-value" style="color: {COLOR_OTHER};">{metrics['total_invalid']}</div></div>""", unsafe_allow_html=True)
        m_cols[3].markdown(f"""<div class="metric-card"><div class="metric-label">Expired</div><div class="metric-value" style="color: {COLOR_OTHER};">{metrics['total_expired']}</div></div>""", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
    with c2:
        st.markdown("##### Distribusi Hasil Sinyal")
        if not metrics['outcome_df'].empty:
            donut_chart = alt.Chart(metrics['outcome_df']).mark_arc(innerRadius=50).encode(
                theta=alt.Theta(field="Count", type="quantitative"),
                color=alt.Color(field="Hasil", type="nominal", scale=alt.Scale(domain=['TP', 'SL', 'invalid', 'expired', 'pending', 'active', 'invalid_tp_hit_first'], range=[COLOR_PROFIT, COLOR_LOSS, COLOR_OTHER, COLOR_OTHER, COLOR_PENDING, COLOR_PENDING, COLOR_OTHER]), legend=alt.Legend(title="Hasil Sinyal")),
                tooltip=['Hasil', 'Count']
            ).properties(height=200, width=200)
            st.altair_chart(donut_chart, use_container_width=True)

def render_trades_tab(df):
    st.markdown("### Histori Trade")
    display_df = df.copy()
    display_df['Net PnL'] = display_df.apply(calculate_pnl, axis=1)
    st.dataframe(display_df[['Waktu', 'Tipe', 'Hasil', 'Entry', 'SL', 'TP', 'Net PnL', 'Alasan', 'Probabilitas']], hide_index=True, use_container_width=True,
        column_config={"Waktu": st.column_config.DatetimeColumn("Waktu", format="YYYY-MM-DD HH:mm"), "Net PnL": st.column_config.NumberColumn("Net PnL", format="$%.2f"), "Probabilitas": st.column_config.ProgressColumn("Probabilitas", format="%.2f", min_value=0, max_value=1),})

# --- MAIN APP ---
def main():
    st.set_page_config(page_title="Trading Dashboard", layout="wide")
    load_css()
    st_autorefresh(interval=60 * 1000, key="data_refresher")
    st.title("📈 Trading Performance Dashboard")
    
    df = load_signals()
    if df.empty:
        st.warning("File sinyal_trading.json kosong atau tidak ditemukan."); st.stop()

    if 'Hasil' not in df.columns: df['Hasil'] = None
    df['Hasil'] = df['Hasil'].fillna('pending')
    for col in ['Entry', 'SL', 'TP', 'Probabilitas']:
        if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    outcome_df = df['Hasil'].value_counts().reset_index(); outcome_df.columns = ['Hasil', 'Count']
    total_signals = len(df)
    total_win = (df['Hasil'] == "TP").sum()
    total_loss = (df['Hasil'] == "SL").sum()
    total_invalid = df['Hasil'].str.contains('invalid', na=False).sum()
    total_expired = (df['Hasil'] == "expired").sum()
    executed_trades = total_win + total_loss
    df['Net_PnL'] = df.apply(calculate_pnl, axis=1)
    
    metrics = {'total_pnl': df[df['Hasil'].isin(['TP', 'SL'])]['Net_PnL'].sum(), 'win_rate': (total_win / executed_trades * 100) if executed_trades > 0 else 0, 'execution_rate': (executed_trades / total_signals * 100) if total_signals > 0 else 0, 'total_signals': total_signals, 'total_win': total_win, 'total_loss': total_loss, 'total_invalid': total_invalid, 'total_expired': total_expired, 'outcome_df': outcome_df}
    
    render_holistic_summary(metrics)

    st.markdown("### Live Chart TradingView")
    tradingview_widget_html = f"""
    <div class="tradingview-widget-container" style="height:100%;width:100%">
      <div class="tradingview-widget-container__widget" style="height:calc(100% - 32px);width:100%"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js" async>
      {{
      "width": "100%", "height": 568, "symbol": "BINANCE:BTCUSD", "interval": "15",
      "timezone": "Asia/Jakarta", "theme": "dark", "style": "1", "locale": "en",
      "backgroundColor": "rgba(0, 0, 0, 1)", "gridColor": "rgba(0, 0, 0, 0.06)",
      "hide_top_toolbar": true, "allow_symbol_change": false, "support_host": "https://www.tradingview.com"
    }}
      </script>
    </div>
    """
    components.html(tradingview_widget_html, height=600, scrolling=False)
    
    st.markdown("### Analisis Mendalam")
    tabs = st.tabs(["Trades", "PnL per Minggu", "PnL Kumulatif", "Rata-rata Win/Loss"])
    
    with tabs[0]: render_trades_tab(df)
    
    chart_df = df[df['Hasil'].isin(['TP', 'SL'])].copy()
    if not chart_df.empty:
        chart_df = chart_df.sort_values('Waktu'); chart_df['Cum_PnL'] = chart_df['Net_PnL'].cumsum()
        
        with tabs[1]:
            st.markdown("##### PnL per Minggu"); weekly_pnl = chart_df.set_index('Waktu').resample('W-MON')['Net_PnL'].sum().reset_index()
            if not weekly_pnl.empty:
                weekly_pnl['WeekDisplay'] = weekly_pnl['Waktu'].apply(lambda d: f"{d.strftime('%b %d')} - {(d + timedelta(days=6)).strftime('%b %d')}")
                weekly_chart = alt.Chart(weekly_pnl).mark_bar(size=20).encode(x=alt.X('WeekDisplay:N', title="Minggu", sort=alt.EncodingSortField(field="Waktu"), axis=alt.Axis(labelAngle=0)), y=alt.Y('Net_PnL:Q', title="Net PnL"), color=alt.condition(alt.datum.Net_PnL > 0, alt.value(COLOR_PROFIT), alt.value(COLOR_LOSS)), tooltip=['WeekDisplay', alt.Tooltip('Net_PnL', format='$,.2f')]).properties(height=300)
                st.altair_chart(weekly_chart, use_container_width=True)
        
        with tabs[2]:
            st.markdown("##### PnL Kumulatif"); base = alt.Chart(chart_df).encode(x=alt.X("Waktu:T", title="Tanggal", axis=alt.Axis(labelAngle=0)), y=alt.Y("Cum_PnL:Q", title="Cumulative PnL", scale=alt.Scale(zero=True)), tooltip=[alt.Tooltip("Waktu:T", format='%Y-%m-%d %H:%M', title="Waktu"), alt.Tooltip("Cum_PnL:Q", format='$,.2f', title="PnL Kumulatif")]); area_layer = base.mark_area(opacity=0.3, color=COLOR_LINE); line_layer = base.mark_line(color=COLOR_LINE); cumulative_chart = (area_layer + line_layer).properties(height=300).interactive(); st.altair_chart(cumulative_chart, use_container_width=True)
        
        with tabs[3]:
            st.markdown("##### Rata-rata Win vs Loss"); win_avg = chart_df[chart_df['Net_PnL'] > 0]['Net_PnL'].mean(); loss_avg = chart_df[chart_df['Net_PnL'] < 0]['Net_PnL'].mean(); avg_data = pd.DataFrame([{'Jenis': 'Rata-rata Win', 'Nilai': win_avg}, {'Jenis': 'Rata-rata Loss', 'Nilai': loss_avg}]).fillna(0); avg_chart = alt.Chart(avg_data).mark_bar(size=20).encode(x=alt.X('Jenis:N', title=None, sort=None, axis=alt.Axis(labelAngle=0)), y=alt.Y('Nilai:Q', title="Rata-rata PnL"), color=alt.condition(alt.datum.Nilai > 0, alt.value(COLOR_PROFIT), alt.value(COLOR_LOSS)), tooltip=['Jenis', alt.Tooltip('Nilai', format='$,.2f')]).properties(height=300); st.altair_chart(avg_chart, use_container_width=True)

if __name__ == "__main__":
    main()