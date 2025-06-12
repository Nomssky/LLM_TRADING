import streamlit as st
import pandas as pd
import json
from datetime import datetime
import altair as alt
from streamlit_autorefresh import st_autorefresh

# --- KONFIGURASI UTAMA ---
JSON_FILE = "sinyal_trading.json"
PNL_MULTIPLIER = 0.01
COMMISSION_PER_TRADE = 0.0

# Warna kustom
COLOR_PROFIT = '#2ecc71'
COLOR_LOSS = '#e74c3c'
COLOR_LINE = '#3498db'

# --- FUNGSI-FUNGSI BANTUAN ---

def load_css():
    """Memuat CSS kustom untuk tampilan dashboard."""
    st.markdown(
        """
        <style>
        .main .block-container {
            padding-top: 1rem !important;
            padding-left: 2rem !important;
            padding-right: 2rem !important;
            padding-bottom: 2rem !important;
        }
        h1 { margin-top: 0 !important; padding-top: 0 !important; }
        h3 {
            margin-top: 1.5rem !important;
            margin-bottom: 0.75rem !important;
            padding: 0 !important;
        }
        .metric-container {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 1rem;
            margin-bottom: 1rem;
        }
        .metric-card {
            background-color: #2a2a2a;
            border-radius: 8px;
            padding: 1rem;
            text-align: center;
        }
        .metric-label { font-size: 0.9rem; color: #a0a0a0; margin-bottom: 0.5rem; }
        .metric-value { font-size: 1.5rem; font-weight: bold; }
        .table-container { overflow: auto; }
        </style>
        """, unsafe_allow_html=True
    )

def load_signals():
    try:
        df = pd.read_json(JSON_FILE)
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
        if hasil == "TP":
            pnl = abs((tp - entry) if "BUY" in tipe else (entry - tp)) * PNL_MULTIPLIER
        elif hasil == "SL":
            pnl = -abs((sl - entry) if "BUY" in tipe else (entry - sl)) * PNL_MULTIPLIER
        else: pnl = 0.0
        return pnl
    except: return 0.0

def create_summary_chart(df, period_col, display_col, title, sort_values=None):
    if df.empty:
        st.info(f"Tidak ada data untuk ringkasan {title}.")
        return

    if display_col:
        summary = df.groupby([period_col, display_col])['Net_PnL'].sum().reset_index()
        sort_instruction = alt.EncodingSortField(field=period_col, op="min", order="ascending")
        x_axis_col = f'{display_col}:N'
    else:
        summary = df.groupby(period_col)['Net_PnL'].sum().reset_index()
        sort_instruction = sort_values
        x_axis_col = f'{period_col}:N'

    chart = alt.Chart(summary).mark_bar(size=40).encode(
        x=alt.X(x_axis_col, sort=sort_instruction, title=None, axis=alt.Axis(labelAngle=0, labelColor='white')),
        y=alt.Y('Net_PnL:Q', title="Net PnL", axis=alt.Axis(titleColor='white', labelColor='white', grid=True, gridColor='#444')),
        color=alt.condition(alt.datum.Net_PnL > 0, alt.value(COLOR_PROFIT), alt.value(COLOR_LOSS)),
        tooltip=[alt.Tooltip(x_axis_col.split(':')[0], title=title), alt.Tooltip('Net_PnL:Q', title='Total PnL', format='$.2f')]
    ).properties(height=300, background='transparent').configure_view(strokeOpacity=0)
    
    st.altair_chart(chart, use_container_width=True)

def render_metrics_summary(metrics):
    st.markdown("### Ringkasan Performa")
    st.markdown('<div class="metric-container">', unsafe_allow_html=True)
    cols = st.columns(4)
    cols[0].markdown(f"""<div class="metric-card"><div class="metric-label">Total PnL (Closed)</div><div class="metric-value" style="color: {'{COLOR_PROFIT}' if metrics['total_pnl'] >= 0 else '{COLOR_LOSS}'};">${metrics['total_pnl']:,.2f}</div></div>""", unsafe_allow_html=True)
    cols[1].markdown(f"""<div class="metric-card"><div class="metric-label">Win Rate</div><div class="metric-value">{metrics['win_rate']:.2f}%</div></div>""", unsafe_allow_html=True)
    cols[2].markdown(f"""<div class="metric-card"><div class="metric-label">Total Wins</div><div class="metric-value" style="color: {COLOR_PROFIT};">{metrics['total_win']}</div></div>""", unsafe_allow_html=True)
    cols[3].markdown(f"""<div class="metric-card"><div class="metric-label">Total Losses</div><div class="metric-value" style="color: {COLOR_LOSS};">{metrics['total_loss']}</div></div>""", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

def render_trades_tab(df):
    st.markdown("### Histori Trade")
    
    display_df = df.copy()
    display_df['Display_PnL'] = display_df.apply(calculate_pnl, axis=1) - COMMISSION_PER_TRADE
    
    columns_to_show = ['Trade #', 'Type', 'Waktu', 'Entry', 'SL', 'TP', 'Net PnL', 'Status Trade', 'Setup']
    display_df = display_df.rename(columns={'Tipe': 'Type', 'Alasan': 'Setup', 'Status': 'Status Trade', 'Display_PnL': 'Net PnL'})
    display_df['Trade #'] = range(len(display_df), 0, -1)
    
    if 'Status Trade' in display_df.columns:
         display_df['Live'] = display_df['Status Trade'].apply(lambda x: '🟢' if str(x).lower() == 'active' else '')
         columns_to_show.insert(2, 'Live')

    if 'Probabilitas' in display_df.columns:
        display_df = display_df.rename(columns={'Probabilitas': 'Prob'})
        columns_to_show.insert(8, 'Prob')

    st.markdown('<div class="table-container">', unsafe_allow_html=True)
    st.data_editor(
        display_df[columns_to_show],
        hide_index=True, use_container_width=True, disabled=True,
        column_config={
            "Waktu": st.column_config.DatetimeColumn("Waktu", format="YYYY-MM-DD HH:mm"),
            "Entry": st.column_config.NumberColumn(format="$%.2f"),
            "SL": st.column_config.NumberColumn(format="$%.2f"),
            "TP": st.column_config.NumberColumn(format="$%.2f"),
            "Net PnL": st.column_config.NumberColumn(format="$%.2f"),
            "Prob": st.column_config.ProgressColumn(help="Probabilitas", format="%d%%", min_value=0, max_value=100),
        }
    )
    st.markdown('</div>', unsafe_allow_html=True)

# --- MAIN APP ---
def main():
    st.set_page_config(page_title="Trading Dashboard", layout="wide")
    load_css()
    st_autorefresh(interval=30 * 1000, key="data_refresher")

    st.title("📈 Trading Performance Dashboard")
    
    df = load_signals()
    if df.empty:
        st.warning("File sinyal_trading.json kosong atau tidak ditemukan."); st.stop()

    with st.sidebar:
        st.markdown("## 🗓️ Filter Tanggal")
        min_date, max_date = df['Waktu'].min().date(), df['Waktu'].max().date()
        start_date = st.date_input("Mulai", min_date, min_value=min_date, max_value=max_date)
        end_date = st.date_input("Selesai", max_date, min_value=min_date, max_value=max_date)

    if start_date > end_date:
        st.error("Tanggal mulai harus sebelum tanggal selesai."); st.stop()

    mask = (df['Waktu'].dt.date >= start_date) & (df['Waktu'].dt.date <= end_date)
    filtered_df = df.loc[mask].copy()

    if filtered_df.empty:
        st.warning("Tidak ada data sinyal dalam rentang tanggal yang dipilih."); st.stop()

    for col in ['Entry', 'SL', 'TP']:
        if col in filtered_df.columns:
            filtered_df[col] = pd.to_numeric(filtered_df[col], errors='coerce').fillna(0)

    # --- PERBAIKAN FINAL UNTUK SKALA PROBABILITAS ---
    if 'Probabilitas' in filtered_df.columns:
        # Konversi ke numerik, tangani error
        s = pd.to_numeric(filtered_df['Probabilitas'], errors='coerce').fillna(0)
        # Cek baris mana yang skalanya 0-1 (misal: 0.8) dan kalikan dengan 100
        filtered_df['Probabilitas'] = s.where(s > 1, s * 100)
    
    valid_stats_df = filtered_df[filtered_df['Hasil'].isin(['TP', 'SL'])].copy()
    if not valid_stats_df.empty:
        valid_stats_df['Net_PnL'] = valid_stats_df.apply(calculate_pnl, axis=1) - COMMISSION_PER_TRADE
        valid_stats_df = valid_stats_df.sort_values('Waktu')
        valid_stats_df['Cum_PnL'] = valid_stats_df['Net_PnL'].cumsum()
    
    total_win = (valid_stats_df['Hasil'] == "TP").sum() if not valid_stats_df.empty else 0
    total_loss = (valid_stats_df['Hasil'] == "SL").sum() if not valid_stats_df.empty else 0
    valid_trades = total_win + total_loss
    metrics = {
        'total_pnl': valid_stats_df['Net_PnL'].sum() if not valid_stats_df.empty else 0,
        'win_rate': (total_win / valid_trades * 100) if valid_trades > 0 else 0,
        'total_win': total_win,
        'total_loss': total_loss
    }

    render_metrics_summary(metrics)

    tab_names = ["Trades", "Weekly PnL", "Monthly PnL", "Cumulative PnL", "Win/Loss Avg", "PnL by Day"]
    tabs = st.tabs(tab_names)

    with tabs[0]: render_trades_tab(filtered_df)
    
    # Sisa tabs untuk chart
    if not valid_stats_df.empty:
        with tabs[1]:
            st.markdown("### PnL by Week")
            df_copy = valid_stats_df.copy()
            df_copy['YearWeek'] = df_copy['Waktu'].dt.strftime('%Y-W%U')
            df_copy['WeekDisplay'] = df_copy['Waktu'].dt.to_period('W').apply(lambda p: f"{p.start_time.strftime('%b %d')} - {p.end_time.strftime('%b %d')}")
            create_summary_chart(df_copy, 'YearWeek', 'WeekDisplay', 'Minggu')

        with tabs[2]:
            st.markdown("### PnL by Month")
            df_copy = valid_stats_df.copy()
            df_copy['YearMonth'] = df_copy['Waktu'].dt.strftime('%Y-%m')
            df_copy['MonthDisplay'] = df_copy['Waktu'].dt.strftime('%B %Y')
            create_summary_chart(df_copy, 'YearMonth', 'MonthDisplay', 'Bulan')

        with tabs[3]:
            st.markdown("### Cumulative PnL")
            line_chart = alt.Chart(valid_stats_df).mark_line(point=alt.OverlayMarkDef(color=COLOR_LINE), color=COLOR_LINE).encode(
                x=alt.X("Waktu:T", title=None, axis=alt.Axis(format='%b %d', labelAngle=0, labelColor='white')),
                y=alt.Y("Cum_PnL:Q", title="Cumulative PnL", axis=alt.Axis(titleColor='white', labelColor='white', grid=True, gridColor='#444'), scale=alt.Scale(zero=True)),
                tooltip=[alt.Tooltip("Waktu:T", format='%Y-%m-%d %H:%M'), alt.Tooltip("Cum_PnL:Q", format='$.2f')]
            ).properties(height=300, background='transparent').configure_view(strokeOpacity=0).interactive()
            st.altair_chart(line_chart, use_container_width=True)

        with tabs[4]:
            st.markdown("### Win/Loss Average")
            win_avg = valid_stats_df[valid_stats_df['Hasil'] == 'TP']['Net_PnL'].mean()
            loss_avg = valid_stats_df[valid_stats_df['Hasil'] == 'SL']['Net_PnL'].mean()
            avg_data = pd.DataFrame({'Outcome': ['Average Win', 'Average Loss'], 'Net_PnL': [win_avg, loss_avg]}).fillna(0)
            create_summary_chart(avg_data, 'Outcome', None, 'Rata-rata')

        with tabs[5]:
            st.markdown("### PnL by Day")
            df_copy = valid_stats_df.copy()
            day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            df_copy['DayOfWeek'] = pd.Categorical(df_copy['Waktu'].dt.day_name(), categories=day_order, ordered=True)
            create_summary_chart(df_copy, 'DayOfWeek', None, 'Hari', sort_values=day_order)
    else:
        for i in range(1, 6):
            with tabs[i]:
                st.info("Tidak ada trade selesai untuk ditampilkan pada chart.")


if __name__ == "__main__":
    main()