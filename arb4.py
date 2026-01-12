import streamlit as st
import akshare as ak
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np

# 设置网页标题
st.set_page_config(page_title="跨品种套利看板", layout="wide")

# 1. 配置套利组合及推荐参数
arbitrage_config = {
    "焦化利润 (J - 1.3*JM)": {
        "leg_a": "J0", "leg_b": "JM0", "coeff_a": 1, "coeff_b": -1.3, 
        "name_a": "焦炭", "name_b": "焦煤",
        "def_window": 40, "def_std": 2.0, "desc": "推荐长周期，过滤政策性波动"
    },
    "卷螺差 (HC - RB)": {
        "leg_a": "HC0", "leg_b": "RB0", "coeff_a": 1, "coeff_b": -1, 
        "name_a": "热卷", "name_b": "螺纹",
        "def_window": 20, "def_std": 2.0, "desc": "经典工业品套利，20日均线灵敏度适中"
    },
    "塑料姐妹 (PP - L)": {
        "leg_a": "PP0", "leg_b": "L0", "coeff_a": 1, "coeff_b": -1, 
        "name_a": "PP", "name_b": "塑料",
        "def_window": 15, "def_std": 1.8, "desc": "强替代性品种，建议更窄的通道与更短的周期"
    },
    "烯烃利润 (PP - 3*MA)": {
        "leg_a": "PP0", "leg_b": "MA0", "coeff_a": 1, "coeff_b": -3, 
        "name_a": "PP", "name_b": "甲醇",
        "def_window": 30, "def_std": 2.5, "desc": "受原油及成本影响大，高波动，需宽通道防错"
    },
    "豆类溢价 (A - B)": {
        "leg_a": "A0", "leg_b": "B0", "coeff_a": 1, "coeff_b": -1, 
        "name_a": "豆一", "name_b": "豆二",
        "def_window": 100, "def_std": 2.0, "desc": "关注政策支撑位，标准参数即可"
    }
}

st.title("📊 期货套利全维度实时监控")

# 2. 侧边栏
selected_pair = st.sidebar.selectbox("切换套利组合", list(arbitrage_config.keys()))
config = arbitrage_config[selected_pair]
st.sidebar.info(f"**策略逻辑：**\n{config['desc']}")

window = st.sidebar.slider("时间窗口 (Window)", 5, 120, config['def_window'])
num_std = st.sidebar.slider("标准差倍数 (K)", 1.0, 3.5, config['def_std'], 0.1)

@st.cache_data(ttl=3600)
def get_data(symbol):
    try:
        df = ak.futures_main_sina(symbol=symbol)
        df['日期'] = pd.to_datetime(df['日期'])
        return df[['日期', '收盘价']].rename(columns={'日期': 'date', '收盘价': symbol})
    except: return pd.DataFrame()

with st.spinner('正在同步数据...'):
    df_a = get_data(config['leg_a'])
    df_b = get_data(config['leg_b'])

    if not df_a.empty and not df_b.empty:
        df = pd.merge(df_a, df_b, on='date', how='inner').sort_values('date')
        df['spread'] = df[config['leg_a']] * config['coeff_a'] + df[config['leg_b']] * config['coeff_b']
        
        # 计算布林带
        df['ma'] = df['spread'].rolling(window=window).mean()
        df['std'] = df['spread'].rolling(window=window).std()
        df['upper'] = df['ma'] + (num_std * df['std'])
        df['lower'] = df['ma'] - (num_std * df['std'])
        
        # 最新数据点
        last_price_a = df[config['leg_a']].iloc[-1]
        last_price_b = df[config['leg_b']].iloc[-1]
        last_spread = df['spread'].iloc[-1]
        last_std = df['std'].iloc[-1]
        last_ma = df['ma'].iloc[-1]
        z_score = (last_spread - last_ma) / last_std if last_std != 0 else 0

        # --- 第一部分：核心指标看板 ---
        st.subheader("📍 实时行情摘要")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric(f"{config['name_a']} 现价", f"{last_price_a:.1f}")
        m2.metric(f"{config['name_b']} 现价", f"{last_price_b:.1f}")
        m3.metric("当前价差 (Spread)", f"{last_spread:.2f}")
        m4.metric("当前 Z-Value", f"{z_score:.2f}", 
                  delta=f"{'超买' if z_score > num_std else '超卖' if z_score < -num_std else '区间内'}",
                  delta_color="inverse")

        # --- 第二部分：灵敏度矩阵 (全展开) ---
        st.markdown("---")
        st.subheader("🔍 灵敏度多维透视 (不同 K 值信号强度)")
        test_ks = [1.0, 1.5, 2.0, 2.5, 3.0]
        cols = st.columns(len(test_ks))
        for i, k in enumerate(test_ks):
            up = last_ma + k * last_std
            lo = last_ma - k * last_std
            if last_spread > up:
                status, color = "🔴 极高/超买", "red"
            elif last_spread < lo:
                status, color = "🔵 极低/超卖", "blue"
            else:
                status, color = "🟢 正常/区间", "gray"
            
            with cols[i]:
                st.markdown(f"**K = {k}**")
                st.markdown(f"<span style='color:{color}; font-size:18px; font-weight:bold;'>{status}</span>", unsafe_allow_html=True)
                st.caption(f"界限: [{lo:.0f}, {up:.0f}]")

        # --- 第三部分：深度可视化图表 ---
        st.markdown("---")
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                           vertical_spacing=0.08, 
                           subplot_titles=(f"{config['name_a']} 与 {config['name_b']} 走势对比", "价差及动态布林通道"),
                           row_heights=[0.35, 0.65])
        
        # 价格走势
        fig.add_trace(go.Scatter(x=df['date'], y=df[config['leg_a']], name=config['name_a'], line=dict(color='#FF4B4B')), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date'], y=df[config['leg_b']], name=config['name_b'], line=dict(color='#1C83E1')), row=1, col=1)
        
        # 价差布林带
        fig.add_trace(go.Scatter(x=df['date'], y=df['spread'], name="价差", line=dict(color='white', width=2.5)), row=2, col=1)
        fig.add_trace(go.Scatter(x=df['date'], y=df['upper'], name="上轨", line=dict(color='red', width=1, dash='dash')), row=2, col=1)
        fig.add_trace(go.Scatter(x=df['date'], y=df['lower'], name="下轨", line=dict(color='green', width=1, dash='dash')), row=2, col=1)
        fig.add_trace(go.Scatter(x=df['date'], y=df['ma'], name="均线", line=dict(color='rgba(150,150,150,0.5)')), row=2, col=1)

        fig.update_layout(height=800, template="plotly_dark", hovermode="x unified",
                          margin=dict(l=50, r=50, t=50, b=50))
        st.plotly_chart(fig, use_container_width=True)
        
    else:
        st.error("无法加载数据，请确保您的网络可以访问新浪财经接口。")