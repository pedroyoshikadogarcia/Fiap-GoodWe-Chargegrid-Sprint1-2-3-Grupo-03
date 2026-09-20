import streamlit as st
import pandas as pd
import time
import altair as alt

st.set_page_config(page_title="ChargeGrid Intelligence - Sprint 3", layout="centered")

st.title("ChargeGrid Intelligence")
st.caption("GoodWe Challenge - Prova de Conceito Integrada (Sprint 3)")

POTENCIA_CONTRATADA_BASE = 150.0
CAPACIDADE_MAX_CARREGADOR = 22.0

st.sidebar.header("Modo de Operação")
modo_simulacao = st.sidebar.radio("Selecione o Controle", ["Manual", "Simulação Automática (24h)"])


def processar_telemetria(hora_simulada, consumo_predio, geracao_solar, potencia_limite, status_horario):
    estacoes_recarga = {
        "Estacao_01_VanFrota": {"carro_conectado": True, "potencia_atual_kw": CAPACIDADE_MAX_CARREGADOR,
                                "prioridade": "Alta"},
        "Estacao_02_Diretoria": {"carro_conectado": True, "potencia_atual_kw": CAPACIDADE_MAX_CARREGADOR,
                                 "prioridade": "Média"},
        "Estacao_03_Visitante": {"carro_conectado": True, "potencia_atual_kw": CAPACIDADE_MAX_CARREGADOR,
                                 "prioridade": "Baixa"}
    }

    demanda_liquida_predio = max(0.0, consumo_predio - geracao_solar)
    demanda_carregadores_inicial = sum(estacao["potencia_atual_kw"] for estacao in estacoes_recarga.values())
    demanda_total_sistema = demanda_liquida_predio + demanda_carregadores_inicial

    dlb_ativo = False
    logs_dlb = []

    if demanda_total_sistema > potencia_limite:
        dlb_ativo = True
        excesso = demanda_total_sistema - potencia_limite
        ordem_corte = ["Baixa", "Média", "Alta"]

        for prioridade in ordem_corte:
            for nome_estacao, dados in estacoes_recarga.items():
                if dados["prioridade"] == prioridade and dados["potencia_atual_kw"] > 0:
                    if excesso >= dados["potencia_atual_kw"]:
                        excesso -= dados["potencia_atual_kw"]
                        logs_dlb.append(f"Estação '{nome_estacao}' ({prioridade}) DESLIGADA (0 kW).")
                        dados["potencia_atual_kw"] = 0.0
                    else:
                        dados["potencia_atual_kw"] -= excesso
                        logs_dlb.append(
                            f"Estação '{nome_estacao}' ({prioridade}) LIMITADA para {dados['potencia_atual_kw']:.2f} kW.")
                        excesso = 0
                        break
            if excesso <= 0:
                break
    else:
        for dados in estacoes_recarga.values():
            dados["potencia_atual_kw"] = CAPACIDADE_MAX_CARREGADOR

    demanda_carregadores_final = sum(estacao["potencia_atual_kw"] for estacao in estacoes_recarga.values())
    demanda_final_sistema = demanda_liquida_predio + demanda_carregadores_final

    return {
        "hora": hora_simulada,
        "consumo_predio": consumo_predio,
        "geracao_solar": geracao_solar,
        "potencia_limite": potencia_limite,
        "demanda_final": demanda_final_sistema,
        "dlb_ativo": dlb_ativo,
        "logs_dlb": logs_dlb,
        "estacoes": estacoes_recarga,
        "demanda_liquida": demanda_liquida_predio,
        "status_horario": status_horario
    }


def renderizar_dashboard(dados, container):
    with container.container():
        with st.container(border=True):
            col1, col2 = st.columns(2)
            col1.metric("Consumo do Prédio", f"{dados['consumo_predio']:.1f} kW")
            col2.metric("Geração Solar", f"{dados['geracao_solar']:.1f} kW")

            col3, col4 = st.columns(2)
            col3.metric("Demanda Total", f"{dados['demanda_final']:.1f} / {dados['potencia_limite']:.1f} kW")
            if dados['dlb_ativo']:
                col4.metric("Status DLB", "SOBRECARGA", delta="Atuação Dinâmica", delta_color="inverse")
            else:
                col4.metric("Status DLB", "ESTÁVEL", delta="Normal")

        if dados['dlb_ativo']:
            st.error(f"ALERTA DE SOBRECARGA DETECTADO ({dados['hora']}:00h) - ATUANDO VIA PROTOCOLO DLB")
            for log in dados['logs_dlb']:
                st.write(f"-> {log}")
        else:
            st.success(f"STATUS: REDE ESTÁVEL ({dados['hora']}:00h) - Potência dentro dos limites.")

        with st.container(border=True):
            st.subheader(f"Potência Alocada por Estação - {dados['hora']}:00h (kW)")

            nomes_formatados = {
                "Estacao_01_VanFrota": "E1 - Van Frota",
                "Estacao_02_Diretoria": "E2 - Diretoria",
                "Estacao_03_Visitante": "E3 - Visitante"
            }

            df_grafico = pd.DataFrame({
                "Estação": [nomes_formatados[k] for k in dados['estacoes'].keys()],
                "Potência": [round(d["potencia_atual_kw"], 2) for d in dados['estacoes'].values()]
            })

            chart = alt.Chart(df_grafico).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
                x=alt.X('Estação:N', title='Estação', sort=None, axis=alt.Axis(labelAngle=0)),
                y=alt.Y('Potência:Q', scale=alt.Scale(domain=[0, 25]), title='Potência (kW)'),
                color=alt.value('#1f77b4')
            ).properties(height=280)

            st.altair_chart(chart, use_container_width=True)

        with st.container(border=True):
            st.subheader("Telemetria de Saída (Payload JSON)")
            telemetria_json = {
                "timestamp": int(time.time()),
                "hora_simulada": f"{dados['hora']}:00h",
                "periodo_operacional": dados['status_horario'],
                "consumo_predio_kw": dados['consumo_predio'],
                "geracao_solar_kw": dados['geracao_solar'],
                "demanda_liquida_kw": dados['demanda_liquida'],
                "limite_contratado_kw": dados['potencia_limite'],
                "dlb_acionado": dados['dlb_ativo'],
                "estacoes_status": {k: {"potencia_kw": round(v["potencia_atual_kw"], 2), "prioridade": v["prioridade"]}
                                    for k, v in dados['estacoes'].items()}
            }
            st.json(telemetria_json)


painel_dinamico = st.empty()

if modo_simulacao == "Simulação Automática (24h)":
    iniciar = st.sidebar.button("Play na Simulação (00h às 23h)")

    if iniciar:
        for h in range(24):
            if h == 17:
                status_h = "TRANSIÇÃO FIM DE TARDE"
                c_predio = 95.0
                g_solar = 10.0
                p_limite = POTENCIA_CONTRATADA_BASE
            elif h == 18:
                status_h = "INÍCIO HORÁRIO DE PICO"
                c_predio = 110.0
                g_solar = 0.0
                p_limite = POTENCIA_CONTRATADA_BASE
            elif h == 19:
                status_h = "PICO INTERMEDIÁRIO"
                c_predio = 128.0
                g_solar = 0.0
                p_limite = POTENCIA_CONTRATADA_BASE
            elif h == 20:
                status_h = "PICO MÁXIMO"
                c_predio = 142.0
                g_solar = 0.0
                p_limite = POTENCIA_CONTRATADA_BASE
            elif h == 21:
                status_h = "ALÍVIO DO PICO"
                c_predio = 115.0
                g_solar = 0.0
                p_limite = POTENCIA_CONTRATADA_BASE
            elif 6 <= h < 17:
                status_h = "FORA DE PICO (DIURNO)"
                c_predio = 85.0
                g_solar = 65.0 if 10 <= h <= 15 else 30.0
                p_limite = POTENCIA_CONTRATADA_BASE
            else:
                status_h = "FORA DE PICO (NOTURNO)"
                c_predio = 40.0
                g_solar = 0.0
                p_limite = POTENCIA_CONTRATADA_BASE

            res = processar_telemetria(h, c_predio, g_solar, p_limite, status_h)
            renderizar_dashboard(res, painel_dinamico)
            time.sleep(1.0)
    else:
        res = processar_telemetria(12, 85.0, 65.0, POTENCIA_CONTRATADA_BASE, "FORA DE PICO (DIURNO)")
        renderizar_dashboard(res, painel_dinamico)
else:
    st.sidebar.header("Parâmetros do Prédio")
    p_limite = st.sidebar.number_input("Potência Contratada (kW)", value=POTENCIA_CONTRATADA_BASE, step=10.0)
    st.sidebar.header("Telemetria de Entrada")
    g_solar = st.sidebar.slider("Geração Solar Fotovoltaica (kW)", 0.0, 100.0, 45.0)
    c_predio = st.sidebar.slider("Consumo do Prédio (kW)", 50.0, 180.0, 130.0)

    res = processar_telemetria(12, c_predio, g_solar, p_limite, "MANUAL")
    renderizar_dashboard(res, painel_dinamico)