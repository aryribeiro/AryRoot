# app.py
import streamlit as st
from core import setup_data_directory
from professor import render_teacher_login, render_teacher_dashboard, render_teacher_game_control, render_teacher_signup, render_upload_questions_json_page # Adicionada importação
from aluno import render_student_home, render_waiting_room, render_game, render_game_results
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# Configurações da página
st.set_page_config(
    page_title="AryRoot | Quiz Game Multiplayer",
    page_icon="🎮",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Estilos CSS personalizados
st.markdown("""
<style>
    .main {
        background: linear-gradient(to bottom, #e0f7fa, #ffffff);
        padding: 20px;
    }
    .stButton > button {
        background-color: #4CAF50;
        color: white;
        font-weight: bold;
        border-radius: 12px;
        padding: 12px 24px;
        border: none;
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        transition: all 0.3s ease;
    }
    .stButton > button:hover {
        background-color: #45a049;
        box-shadow: 0 6px 12px rgba(0,0,0,0.15);
        transform: translateY(-2px);
    }
    .title {
        color: #2E7D32;
        text-align: center;
        font-size: 3.5rem;
        margin-bottom: 2rem;
        font-weight: bold;
        text-shadow: 1px 1px 2px rgba(0,0,0,0.1);
    }
    .podium {
        display: flex;
        justify-content: center;
        align-items: flex-end;
        margin: 30px 0;
        gap: 20px;
        animation: slide-up 0.5s ease-out;
    }
    .podium-place {
        text-align: center;
        transition: transform 0.3s ease;
    }
    .podium-place:hover {
        transform: scale(1.05);
    }
    .first-place {
        background: linear-gradient(to bottom, #ffd700, #f0c14b);
        width: 160px;
        height: 280px;
        border-radius: 12px;
        box-shadow: 0 6px 12px rgba(0,0,0,0.2);
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        position: relative;
        z-index: 3;
    }
    .second-place {
        background: linear-gradient(to bottom, #c0c0c0, #a8a8a8);
        width: 140px;
        height: 220px;
        border-radius: 12px;
        box-shadow: 0 6px 12px rgba(0,0,0,0.2);
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        position: relative;
        z-index: 2;
    }
    .third-place {
        background: linear-gradient(to bottom, #cd7f32, #b87333);
        width: 120px;
        height: 160px;
        border-radius: 12px;
        box-shadow: 0 6px 12px rgba(0,0,0,0.2);
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        position: relative;
        z-index: 1;
    }
    .podium-icon {
        font-size: 2.5rem;
        margin-bottom: 10px;
    }
    .podium-name {
        font-size: 1.2rem;
        font-weight: bold;
        color: #ffffff;
        text-shadow: 1px 1px 2px rgba(0,0,0,0.3);
    }
    .podium-score {
        font-size: 1rem;
        color: #f0f0f0;
    }
    .ranking-table {
        width: 100%;
        max-width: 700px;
        margin: 20px auto;
        border-collapse: collapse;
        background-color: #ffffff;
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        border-radius: 8px;
        overflow: hidden;
    }
    .ranking-table th, .ranking-table td {
        padding: 12px;
        text-align: center;
        border-bottom: 1px solid #e0e0e0;
    }
    .ranking-table th {
        background-color: #2E7D32;
        color: white;
        font-weight: bold;
    }
    .ranking-table tr:nth-child(even) {
        background-color: #f9f9f9;
    }
    .ranking-table tr.current-player {
        background-color: #e0f7fa;
        font-weight: bold;
    }
    .ranking-table .medal {
        font-size: 1.2rem;
        margin-right: 8px;
    }
    .big-input {
        font-size: 24px !important;
        text-align: center !important;
        height: 60px !important;
    }
    .icon-selection {
        display: flex;
        justify-content: center;
        flex-wrap: wrap;
        gap: 10px;
    }
    .icon-button {
        background: none;
        border: 2px solid transparent;
        cursor: pointer;
        font-size: 2rem;
        padding: 5px;
        border-radius: 50%;
        transition: all 0.3s;
    }
    .icon-button.selected {
        border-color: #4CAF50;
        background-color: rgba(76, 175, 80, 0.1);
    }
    .countdown {
        font-size: 4rem;
        text-align: center;
        color: #2E7D32;
        font-weight: bold;
    }
    .player-icon {
        font-size: 2rem;
        margin-right: 10px;
    }
    .question-number {
        text-align: center;
        font-size: 1.5rem;
        margin-bottom: 1rem;
        color: #555;
    }
    .question-text {
        font-size: 2rem;
        text-align: center;
        margin-bottom: 2rem;
        font-weight: bold;
    }
    .option-button {
        margin: 10px 0;
        padding: 15px;
        width: 100%;
        text-align: center;
        border-radius: 10px;
        cursor: pointer;
        font-size: 1.2rem;
        transition: background-color 0.3s;
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
    }
    .option-button:hover {
        opacity: 0.9;
    }
    .option-1 {
        background-color: #E57373;
        color: white;
    }
    .option-2 {
        background-color: #64B5F6;
        color: white;
    }
    .option-3 {
        background-color: #FFD54F;
        color: black;
    }
    .option-4 {
        background-color: #81C784;
        color: white;
    }
    .result-correct {
        color: #2E7D32;
        font-size: 2rem;
        text-align: center;
        margin-top: 1rem;
    }
    .result-incorrect {
        color: #C62828;
        font-size: 2rem;
        text-align: center;
        margin-top: 1rem;
    }
    .stApp .block-container {
        margin-left: auto;
        margin-right: auto;
        max-width: 900px;
    }
    @keyframes slide-up {
        from {
            opacity: 0;
            transform: translateY(50px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
</style>
""", unsafe_allow_html=True)

# Inicializar arquivos de dados
setup_data_directory()

# Função para inicializar sessão
def init_session_state():
    if "page" not in st.session_state:
        st.session_state.page = "home"
    if "user_type" not in st.session_state:
        st.session_state.user_type = None
    if "username" not in st.session_state:
        st.session_state.username = None
    if "game_code" not in st.session_state:
        st.session_state.game_code = None
    if "selected_icon" not in st.session_state:
        st.session_state.selected_icon = None
    if "answer_time" not in st.session_state:
        st.session_state.answer_time = None
    if "show_ranking" not in st.session_state:
        st.session_state.show_ranking = False
    if "selected_answer" not in st.session_state:
        st.session_state.selected_answer = None

# Navegar para uma página
def navigate_to(page):
    st.session_state.page = page

# Página Inicial
def render_home():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<p style='text-align: center; font-size: 52px; margin-bottom: 0px;'><strong>🎮AryRoot</strong></p>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; font-size: 24px; margin-bottom: 0px;'><strong> Quiz Game Multiplayer</strong></p>", unsafe_allow_html=True)
        tab1, tab2 = st.tabs(["Estudante", "Professor"])
        with tab1:
            render_student_home()
        with tab2:
            render_teacher_login()

# Função principal
def main():
    init_session_state()
    if st.session_state.page == "home":
        render_home()
    elif st.session_state.page == "waiting_room":
        render_waiting_room()
    elif st.session_state.page == "teacher_dashboard":
        render_teacher_dashboard()
    elif st.session_state.page == "teacher_game_control":
        render_teacher_game_control()
    elif st.session_state.page == "game":
        render_game()
    elif st.session_state.page == "game_results":
        render_game_results()
    elif st.session_state.page == "teacher_signup":
        render_teacher_signup()
    elif st.session_state.page == "teacher_upload_json": # Nova rota
        render_upload_questions_json_page()

if __name__ == "__main__":
    main()

st.markdown("""
<hr>
<div style="text-align: center;">
    💬 Por <strong>Ary Ribeiro</strong>. Contato via email: <a href="mailto:aryribeiro@gmail.com">aryribeiro@gmail.com</a><br><br>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<style>
/* Esconde completamente todos os elementos da barra padrão do Streamlit */
    header {display: none !important;}
    footer {display: none !important;}
    #MainMenu {display: none !important;}
    
    /* Remove o espaço em branco no topo do app */
    .reportview-container .main .block-container {
        padding-top: 0rem;
    }
    /* Para versões mais recentes do Streamlit, use este seletor */
    .block-container {
        padding-top: 0rem !important;
    }
/* Remove o espaço em branco no rodapé */
    .reportview-container .main .block-container,
    .block-container {
    padding-bottom: 0rem !important;
    margin-bottom: 0rem !important;
}
</style>
""", unsafe_allow_html=True)