# professor.py
import streamlit as st
from core import Teacher, Game, generate_game_code, SAMPLE_QUESTIONS
import bcrypt
import json
import os
import random
import time
import threading
from datetime import datetime
from typing import Optional

# Cache local para dados do professor
professor_cache = {}
cache_lock = threading.RLock()

def navigate_to(page):
    st.session_state.page = page

# Função para cache local do professor
def get_cached_teacher(username: str) -> Optional[Teacher]:
    with cache_lock:
        cached_data = professor_cache.get(username)
        if cached_data and (datetime.now() - cached_data['timestamp']).total_seconds() < 300:  # 5 minutos
            return cached_data['teacher']
    return None

def cache_teacher(teacher: Teacher):
    with cache_lock:
        professor_cache[teacher.username] = {
            'teacher': teacher,
            'timestamp': datetime.now()
        }

# Operações resilientes para professor
def resilient_teacher_operation(func, max_retries=3):
    """Wrapper para operações de professor com retry"""
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(0.5 * (2 ** attempt))  # Backoff exponencial
                continue
            else:
                st.error(f"Erro na operação: {str(e)}")
                return None

# Sistema de Captcha otimizado
class CaptchaManager:
    def __init__(self):
        self._lock = threading.RLock()
    
    def generate_captcha(self):
        with self._lock:
            num1 = random.randint(1, 10)
            num2 = random.randint(1, 10)
            operation = random.choice(["+", "-"])
            
            if operation == "+":
                question = f"{num1} + {num2}?"
                answer = num1 + num2
            else:
                if num1 < num2:
                    num1, num2 = num2, num1
                question = f"{num1} - {num2}?"
                answer = num1 - num2
            
            st.session_state.captcha_question = question
            st.session_state.captcha_answer = answer

captcha_manager = CaptchaManager()

def render_teacher_login():
    st.markdown("<p style='text-align: center; font-size: 24px; margin-bottom: 10px;'><strong>🔐 Login do Professor</strong></p>", unsafe_allow_html=True)
    
    # Gerar captcha se não existir
    if "captcha_question" not in st.session_state:
        captcha_manager.generate_captcha()
    
    _, central_column, _ = st.columns([0.75, 2.5, 0.75])
    
    with central_column:
        # Form para evitar múltiplas submissões
        with st.form("teacher_login_form", clear_on_submit=False):
            login_username = st.text_input("Nome de usuário", key="login_username")
            login_password = st.text_input("Senha", type="password", key="login_password")
            
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown(f"**Verificação:** Quanto é **{st.session_state.get('captcha_question', '...')}**?")
            captcha_input = st.text_input("Sua resposta para a verificação", key="captcha_input", placeholder="Digite o resultado")
            
            st.markdown("<br>", unsafe_allow_html=True)
            submitted = st.form_submit_button("Entrar", use_container_width=True)
            
            if submitted:
                # Validar captcha
                try:
                    captcha_answer = int(captcha_input.strip()) if captcha_input.strip() else None
                    if captcha_answer != st.session_state.get("captcha_answer"):
                        st.error("Resposta da verificação incorreta.")
                        captcha_manager.generate_captcha()
                        st.rerun()
                        return
                except ValueError:
                    st.error("Resposta da verificação inválida. Digite apenas números.")
                    captcha_manager.generate_captcha()
                    st.rerun()
                    return
                
                # Validar credenciais
                if not login_username or not login_password:
                    st.error("Preencha todos os campos.")
                    return
                
                def login_operation():
                    # Verificar cache primeiro
                    teacher = get_cached_teacher(login_username)
                    if not teacher:
                        teacher = Teacher.get_by_username(login_username)
                        if teacher:
                            cache_teacher(teacher)
                    
                    if teacher and teacher.password:
                        if bcrypt.checkpw(login_password.encode('utf-8'), teacher.password.encode('utf-8')):
                            return teacher
                    return None
                
                with st.spinner("Autenticando..."):
                    teacher = resilient_teacher_operation(login_operation)
                
                if teacher:
                    # Login bem-sucedido
                    st.session_state.username = login_username
                    st.session_state.user_type = "teacher"
                    st.session_state.login_time = time.time()
                    
                    # Limpar campos de login
                    for key in ["captcha_question", "captcha_answer", "login_username", "login_password", "captcha_input"]:
                        if key in st.session_state:
                            del st.session_state[key]
                    
                    navigate_to("teacher_dashboard")
                    st.rerun()
                else:
                    st.error("Nome de usuário ou senha incorretos.")
                    captcha_manager.generate_captcha()
                    st.rerun()

def render_teacher_signup():
    st.markdown("<h1 class='title'>📝Cadastro de Professor</h1>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form(key="signup_form", clear_on_submit=True):
            username = st.text_input("Nome de usuário", key="signup_username")
            name = st.text_input("Nome completo", key="signup_name")
            email = st.text_input("E-mail", key="signup_email")
            password = st.text_input("Senha", type="password", key="signup_password")
            confirm_password = st.text_input("Confirmar senha", type="password", key="signup_confirm_password")
            
            submit = st.form_submit_button("Cadastrar", use_container_width=True)

            if submit:
                # Validações
                if not all([username, name, email, password, confirm_password]):
                    st.error("Preencha todos os campos.")
                    return
                
                if password != confirm_password:
                    st.error("As senhas não coincidem.")
                    return
                
                if len(password) < 8:
                    st.error("A senha deve ter pelo menos 8 caracteres.")
                    return
                
                # Verificar se usuário já existe
                def check_user_exists():
                    return Teacher.get_by_username(username) is not None
                
                if resilient_teacher_operation(check_user_exists):
                    st.error("Este nome de usuário já está em uso.")
                    return
                
                # Criar professor
                def create_teacher():
                    teacher = Teacher.create(username, password, name, email)
                    teacher.save()
                    cache_teacher(teacher)
                    return teacher
                
                with st.spinner("Cadastrando professor..."):
                    new_teacher = resilient_teacher_operation(create_teacher)
                
                if new_teacher:
                    st.success("Professor cadastrado com sucesso!")
                    
                    # Redirecionamento baseado no tipo de usuário
                    if st.session_state.get("user_type") == "teacher" and st.session_state.get("username") == "professor":
                        navigate_to("teacher_dashboard")
                    else:
                        navigate_to("home")
                    st.rerun()
                else:
                    st.error("Erro ao cadastrar professor. Tente novamente.")

        # Botões de navegação
        st.markdown("<br>", unsafe_allow_html=True)
        if st.session_state.get("user_type") == "teacher" and st.session_state.get("username") == "professor":
            if st.button("Voltar ao Painel do Administrador", key="back_to_admin_dash", use_container_width=True):
                navigate_to("teacher_dashboard")
                st.rerun()
        else:
            if st.button("Ir para Login", key="go_to_login", use_container_width=True):
                navigate_to("home")
                st.rerun()

def render_teacher_dashboard():
    st.markdown("<h1 class='title'>🖥️ Painel do Professor</h1>", unsafe_allow_html=True)
    
    # Verificar autenticação
    if not st.session_state.get("username") or st.session_state.get("user_type") != "teacher":
        st.error("Acesso não autorizado.")
        navigate_to("home")
        st.rerun()
        return
    
    # Renderizar formulários de edição se necessário
    if st.session_state.get("editing_teacher_username"):
        render_edit_teacher_form(st.session_state.editing_teacher_username)
        return
    
    if "editing_question_index" in st.session_state and st.session_state.editing_question_index is not None:
        render_edit_question_form()
        return
    
    # Carregar jogos do professor
    def load_teacher_games():
        return Game.get_by_teacher(st.session_state.username)
    
    teacher_games = resilient_teacher_operation(load_teacher_games) or []
    active_games = [g for g in teacher_games if g.status in ["waiting", "active"]]
    
    # Mostrar jogos ativos
    if active_games:
        st.subheader("🎮 Jogos ativos")
        for game_obj in active_games:
            player_count = len(game_obj.players) if hasattr(game_obj, 'players') and game_obj.players else 0
            status_emoji = "⏳" if game_obj.status == "waiting" else "🟢"
            
            if st.button(
                f"{status_emoji} Jogo {game_obj.code} - {player_count} jogadores ({game_obj.status})", 
                key=f"control_game_{game_obj.code}",
                use_container_width=True
            ):
                st.session_state.game_code = game_obj.code
                navigate_to("teacher_game_control")
                st.rerun()
    
    # Carregar perguntas do professor
    def load_teacher_questions():
        # Verificar cache primeiro
        teacher = get_cached_teacher(st.session_state.username)
        if not teacher:
            teacher = Teacher.get_by_username(st.session_state.username)
            if teacher:
                cache_teacher(teacher)
        
        if teacher:
            return teacher.questions
        return SAMPLE_QUESTIONS if st.session_state.username == "professor" else []
    
    if "temp_questions" not in st.session_state or st.session_state.get("user_for_temp_q") != st.session_state.username:
        st.session_state.temp_questions = resilient_teacher_operation(load_teacher_questions) or []
        st.session_state.user_for_temp_q = st.session_state.username
    
    # Tabs do dashboard
    tab1_title = "Ações e Gerenciamento" if st.session_state.username == "professor" else "Ações do Jogo"
    tab1, tab2 = st.tabs([tab1_title, "Gerenciar Perguntas"])
    
    with tab1:
        render_teacher_actions_tab()
    
    with tab2:
        render_questions_management_tab()

def render_teacher_actions_tab():
    """Renderiza a aba de ações do professor"""
    is_admin = st.session_state.username == "professor"
    
    if is_admin:
        render_admin_actions()
    else:
        render_regular_teacher_actions()

def render_admin_actions():
    """Ações específicas do administrador"""
    col_admin_actions, col_admin_teacher_list = st.columns([1, 2])
    
    with col_admin_actions:
        # Criar novo jogo
        can_create_game = bool(st.session_state.temp_questions)
        if st.button("Criar Novo Jogo (Admin)", disabled=not can_create_game, use_container_width=True):
            if not can_create_game:
                st.warning("Carregue ou adicione perguntas em 'Gerenciar Perguntas' primeiro.")
            else:
                create_new_game()
        
        # Cadastrar novo professor
        if st.button("Cadastrar Novo Professor", use_container_width=True):
            navigate_to("teacher_signup")
            st.rerun()
        
        # Logout
        if st.button("Sair (Admin)", use_container_width=True):
            logout_user()
    
    with col_admin_teacher_list:
        render_teacher_management()

def render_regular_teacher_actions():
    """Ações do professor regular"""
    can_create_game = bool(st.session_state.temp_questions)
    
    if st.button("Criar novo jogo", disabled=not can_create_game, use_container_width=True):
        if not can_create_game:
            st.warning("Adicione perguntas em 'Gerenciar Perguntas' primeiro.")
        else:
            create_new_game()
    
    if st.button("Sair para Home", use_container_width=True):
        logout_user()

def create_new_game():
    """Cria um novo jogo"""
    def game_creation():
        game_code = generate_game_code()
        # Garantir código único
        while Game.get_by_code(game_code):
            game_code = generate_game_code()
        
        new_game = Game(
            game_code, 
            st.session_state.username, 
            questions_json_str=json.dumps(st.session_state.temp_questions)
        )
        new_game.save()
        return new_game
    
    with st.spinner("Criando novo jogo..."):
        new_game = resilient_teacher_operation(game_creation)
    
    if new_game:
        st.session_state.game_code = new_game.code
        navigate_to("teacher_game_control")
        st.rerun()
    else:
        st.error("Erro ao criar jogo. Tente novamente.")

def logout_user():
    """Realiza logout do usuário"""
    # Limpar cache do professor
    username = st.session_state.get("username")
    if username:
        with cache_lock:
            professor_cache.pop(username, None)
    
    # Limpar sessão
    keys_to_preserve = []  # Não preservar nenhuma chave específica
    for key in list(st.session_state.keys()):
        if key not in keys_to_preserve:
            del st.session_state[key]
    
    navigate_to("home")
    st.rerun()

def render_teacher_management():
    """Renderiza o gerenciamento de professores (admin only)"""
    # Gerenciar confirmação de remoção
    if "teacher_to_remove_confirm" in st.session_state:
        teacher_to_remove = st.session_state.teacher_to_remove_confirm
        st.warning(f"Tem certeza que deseja remover o professor '{teacher_to_remove}'?")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Sim, Remover", type="primary", use_container_width=True, key=f"confirm_remove_{teacher_to_remove}"):
                def remove_teacher():
                    return Teacher.delete_by_username(teacher_to_remove)
                
                with st.spinner(f"Removendo professor {teacher_to_remove}..."):
                    success = resilient_teacher_operation(remove_teacher)
                
                if success:
                    st.success(f"Professor '{teacher_to_remove}' removido.")
                    # Limpar cache
                    with cache_lock:
                        professor_cache.pop(teacher_to_remove, None)
                else:
                    st.error(f"Erro ao remover professor '{teacher_to_remove}'.")
                
                del st.session_state.teacher_to_remove_confirm
                st.rerun()
        
        with col2:
            if st.button("Cancelar Remoção", use_container_width=True, key=f"cancel_remove_{teacher_to_remove}"):
                del st.session_state.teacher_to_remove_confirm
                st.rerun()
        
        st.divider()
    
    # Listar professores
    def load_all_teachers():
        return Teacher.get_all_teachers_except_admin()
    
    teachers_to_manage = resilient_teacher_operation(load_all_teachers) or []
    
    if not teachers_to_manage:
        st.info("Nenhum outro professor cadastrado.")
    else:
        st.subheader("Gerenciar Professores")
        for teacher_obj in teachers_to_manage:
            st.markdown(f"**Nome:** {teacher_obj.name} (`{teacher_obj.username}`), **Email:** {teacher_obj.email}")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✏️ Editar", key=f"edit_{teacher_obj.username}", use_container_width=True):
                    st.session_state.editing_teacher_username = teacher_obj.username
                    st.rerun()
            with col2:
                if st.button("🗑️ Remover", key=f"remove_{teacher_obj.username}", type="secondary", use_container_width=True):
                    st.session_state.teacher_to_remove_confirm = teacher_obj.username
                    st.rerun()
            
            st.divider()

def render_questions_management_tab():
    """Renderiza a aba de gerenciamento de perguntas"""
    st.subheader("📚 Minhas perguntas")
    st.markdown("---")
    
    # Botão para upload de JSON
    if st.button("📤 Carregar Perguntas de Arquivo JSON", use_container_width=True):
        navigate_to("teacher_upload_json")
        st.rerun()
    
    st.markdown("---")
    
    # Não mostrar formulário de edição se estivermos editando
    if not ("editing_question_index" in st.session_state and st.session_state.editing_question_index is not None):
        # Listar perguntas existentes
        if not st.session_state.temp_questions:
            st.info("Nenhuma pergunta carregada. Adicione perguntas manualmente ou carregue um arquivo JSON.")
        else:
            for i, question in enumerate(st.session_state.temp_questions):
                question_preview = question.get('question', '')[:60]
                if len(question.get('question', '')) > 60:
                    question_preview += "..."
                
                with st.expander(f"Pergunta {i+1}: {question_preview}"):
                    st.write("**Opções:**")
                    options = question.get('options', [])
                    correct_idx = question.get('correct', 0)
                    
                    for j, option in enumerate(options):
                        is_correct = j == correct_idx
                        st.write(f"{j+1}. {option}{' ✓ (Correta)' if is_correct else ''}")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("✏️ Editar Pergunta", key=f"edit_q_{i}", use_container_width=True):
                            st.session_state.editing_question_index = i
                            st.session_state.editing_question_data = dict(question)
                            st.rerun()
                    
                    with col2:
                        if st.button("🗑️ Remover Pergunta", key=f"remove_q_{i}", type="secondary", use_container_width=True):
                            remove_question(i)
        
        # Formulário para adicionar nova pergunta
        render_add_question_form()

def remove_question(index):
    """Remove uma pergunta específica"""
    def remove_operation():
        st.session_state.temp_questions.pop(index)
        
        # Salvar no banco se não for admin
        if st.session_state.username != "professor":
            teacher = Teacher.get_by_username(st.session_state.username)
            if teacher:
                teacher.questions = st.session_state.temp_questions
                teacher.save()
                cache_teacher(teacher)
        return True
    
    with st.spinner("Removendo pergunta..."):
        success = resilient_teacher_operation(remove_operation)
    
    if success:
        st.success("Pergunta removida!")
    else:
        st.error("Erro ao remover pergunta.")
    
    st.rerun()

def render_add_question_form():
    """Renderiza o formulário para adicionar nova pergunta"""
    st.subheader("➕ Adicionar nova pergunta")
    
    # Gerenciador de instância do formulário
    if 'add_q_form_instance' not in st.session_state:
        st.session_state.add_q_form_instance = 0
    
    form_key = f"add_question_form_{st.session_state.add_q_form_instance}"
    
    with st.form(key=form_key, clear_on_submit=True):
        question_text = st.text_area("Texto da pergunta", key=f"q_text_{form_key}")
        
        # Inputs para as 4 opções
        options_inputs = []
        for k in range(4):
            option_input = st.text_input(f"Opção {k+1}", key=f"q_opt_{k}_{form_key}")
            options_inputs.append(option_input)
        
        # Radio button para resposta correta
        def format_option_label(idx):
            current_value = st.session_state.get(f"q_opt_{idx}_{form_key}", "").strip()
            return current_value if current_value else f"Opção {idx + 1}"
        
        correct_index = st.radio(
            "Resposta correta",
            options=list(range(4)),
            format_func=format_option_label,
            horizontal=True,
            key=f"q_radio_{form_key}"
        )
        
        submitted = st.form_submit_button("Adicionar pergunta", use_container_width=True)
        
        if submitted:
            add_new_question(question_text, options_inputs, correct_index, form_key)

def add_new_question(question_text, options_inputs, correct_index, form_key):
    """Adiciona uma nova pergunta"""
    # Validar inputs
    question_text = question_text.strip()
    options_values = [opt.strip() for opt in options_inputs]
    
    if not question_text:
        st.error("Preencha o texto da pergunta.")
        return
    
    if not all(options_values):
        st.error("Preencha todas as 4 opções de resposta.")
        return
    
    # Criar nova pergunta
    new_question = {
        "question": question_text,
        "options": options_values,
        "correct": correct_index
    }
    
    def save_operation():
        st.session_state.temp_questions.append(new_question)
        
        # Salvar no banco se não for admin
        if st.session_state.username != "professor":
            teacher = Teacher.get_by_username(st.session_state.username)
            if teacher:
                teacher.questions = st.session_state.temp_questions
                teacher.save()
                cache_teacher(teacher)
        return True
    
    with st.spinner("Adicionando pergunta..."):
        success = resilient_teacher_operation(save_operation)
    
    if success:
        st.success("Pergunta adicionada!")
        # Incrementar instância do formulário para limpar campos
        st.session_state.add_q_form_instance += 1
    else:
        st.error("Erro ao adicionar pergunta.")
    
    st.rerun()

def render_edit_teacher_form(teacher_username_to_edit):
    """Renderiza formulário de edição de professor"""
    def load_teacher():
        # Verificar cache primeiro
        teacher = get_cached_teacher(teacher_username_to_edit)
        if not teacher:
            teacher = Teacher.get_by_username(teacher_username_to_edit)
            if teacher:
                cache_teacher(teacher)
        return teacher
    
    teacher_to_edit = resilient_teacher_operation(load_teacher)
    
    if not teacher_to_edit:
        st.error(f"Professor '{teacher_username_to_edit}' não encontrado para edição.")
        if "editing_teacher_username" in st.session_state:
            del st.session_state.editing_teacher_username
        if st.button("Voltar ao Painel", key="back_to_dash_edit_notfound"):
            navigate_to("teacher_dashboard")
            st.rerun()
        return
    
    st.subheader(f"✏️ Editando Professor: {teacher_username_to_edit}")
    
    with st.form(key=f"edit_teacher_form_{teacher_username_to_edit}"):
        new_name = st.text_input("Nome completo", value=teacher_to_edit.name)
        new_email = st.text_input("E-mail", value=teacher_to_edit.email)
        st.text_input("Nome de usuário (não pode ser alterado)", value=teacher_username_to_edit, disabled=True)
        
        st.markdown("---")
        st.markdown("**Alterar Senha (opcional)**")
        new_password = st.text_input("Nova Senha (deixe em branco para não alterar)", type="password")
        confirm_new_password = st.text_input("Confirmar Nova Senha", type="password")
        
        col1, col2 = st.columns(2)
        with col1:
            save_clicked = st.form_submit_button("Salvar Alterações", use_container_width=True, type="primary")
        with col2:
            cancel_clicked = st.form_submit_button("Cancelar", use_container_width=True)
        
        if save_clicked:
            save_teacher_changes(teacher_to_edit, new_name, new_email, new_password, confirm_new_password)
        
        if cancel_clicked:
            if "editing_teacher_username" in st.session_state:
                del st.session_state.editing_teacher_username
            st.rerun()

def save_teacher_changes(teacher, new_name, new_email, new_password, confirm_new_password):
    """Salva alterações do professor"""
    # Validar dados
    teacher.name = new_name.strip()
    teacher.email = new_email.strip()
    
    if new_password:
        if new_password != confirm_new_password:
            st.error("As novas senhas não coincidem.")
            return
        
        if len(new_password) < 8:
            st.error("A nova senha deve ter pelo menos 8 caracteres.")
            return
        
        teacher.password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    # Salvar alterações
    def save_operation():
        teacher.save()
        cache_teacher(teacher)  # Atualizar cache
        return True
    
    with st.spinner("Salvando alterações..."):
        success = resilient_teacher_operation(save_operation)
    
    if success:
        st.success(f"Professor '{teacher.username}' atualizado com sucesso!")
        if new_password:
            st.info("A senha foi alterada.")
        
        if "editing_teacher_username" in st.session_state:
            del st.session_state.editing_teacher_username
        st.rerun()
    else:
        st.error("Erro ao salvar alterações.")

def render_edit_question_form():
    """Renderiza formulário de edição de pergunta"""
    if ("editing_question_index" not in st.session_state or 
        "editing_question_data" not in st.session_state):
        st.error("Erro: Nenhuma pergunta selecionada para edição.")
        clear_editing_state()
        return
    
    q_idx = st.session_state.editing_question_index
    q_data = st.session_state.editing_question_data
    
    st.subheader(f"✏️ Editando Pergunta {q_idx + 1}")
    
    with st.form(key=f"edit_question_form_{q_idx}"):
        edited_question_text = st.text_area("Texto da pergunta", value=q_data.get("question", ""))
        
        # Inputs para opções
        edited_options = []
        for i in range(4):
            option_value = q_data.get("options", [""] * 4)[i] if i < len(q_data.get("options", [])) else ""
            edited_option = st.text_input(f"Opção {i+1}", value=option_value)
            edited_options.append(edited_option)
        
        # Radio para resposta correta
        default_correct = q_data.get("correct", 0)
        if not (0 <= default_correct < 4):
            default_correct = 0
        
        def format_edit_option_label(idx):
            return edited_options[idx].strip() if edited_options[idx].strip() else f"Opção {idx + 1}"
        
        edited_correct_index = st.radio(
            "Resposta correta",
            options=list(range(4)),
            format_func=format_edit_option_label,
            index=default_correct,
            horizontal=True
        )
        
        col1, col2 = st.columns(2)
        with col1:
            save_clicked = st.form_submit_button("Salvar Alterações da Pergunta", use_container_width=True, type="primary")
        with col2:
            cancel_clicked = st.form_submit_button("Cancelar Edição", use_container_width=True)
        
        if save_clicked:
            save_question_changes(q_idx, edited_question_text, edited_options, edited_correct_index)
        
        if cancel_clicked:
            clear_editing_state()
            st.rerun()

def save_question_changes(q_idx, question_text, options, correct_index):
    """Salva alterações da pergunta"""
    # Validar dados
    question_text = question_text.strip()
    options_clean = [opt.strip() for opt in options]
    
    if not question_text or not all(options_clean):
        st.error("Preencha o texto da pergunta e todas as 4 opções.")
        return
    
    # Atualizar pergunta
    updated_question = {
        "question": question_text,
        "options": options_clean,
        "correct": correct_index
    }
    
    def save_operation():
        st.session_state.temp_questions[q_idx] = updated_question
        
        # Salvar no banco se não for admin
        if st.session_state.username != "professor":
            teacher = Teacher.get_by_username(st.session_state.username)
            if teacher:
                teacher.questions = st.session_state.temp_questions
                teacher.save()
                cache_teacher(teacher)
        return True
    
    with st.spinner("Salvando pergunta..."):
        success = resilient_teacher_operation(save_operation)
    
    if success:
        st.success(f"Pergunta {q_idx + 1} atualizada com sucesso!")
        clear_editing_state()
        st.rerun()
    else:
        st.error("Erro ao salvar pergunta.")

def clear_editing_state():
    """Limpa estado de edição"""
    for key in ["editing_question_index", "editing_question_data"]:
        if key in st.session_state:
            del st.session_state[key]

def render_upload_questions_json_page():
    """Renderiza página de upload de perguntas JSON"""
    st.markdown("<h1 class='title'>📤 Carregar Perguntas de Arquivo JSON</h1>", unsafe_allow_html=True)
    
    uploaded_file = st.file_uploader("Escolha um arquivo JSON", type=["json"], key="questions_json_uploader")
    
    if uploaded_file is not None:
        try:
            file_content = uploaded_file.read().decode("utf-8")
            loaded_questions = json.loads(file_content)
            
            if not isinstance(loaded_questions, list):
                st.error("JSON deve ser uma lista de perguntas.")
                return
            
            # Validar estrutura das perguntas
            valid_questions = []
            for i, q_data in enumerate(loaded_questions):
                if not validate_question_structure(q_data, i + 1):
                    return  # Erro já mostrado na função de validação
                
                valid_questions.append({
                    "question": q_data["question"].strip(),
                    "options": [opt.strip() for opt in q_data["options"]],
                    "correct": q_data["correct"]
                })
            
            # Salvar perguntas
            def save_questions():
                st.session_state.temp_questions = valid_questions
                
                if st.session_state.username != "professor":
                    teacher = Teacher.get_by_username(st.session_state.username)
                    if teacher:
                        teacher.questions = st.session_state.temp_questions
                        teacher.save()
                        cache_teacher(teacher)
                return True
            
            with st.spinner("Salvando perguntas carregadas..."):
                success = resilient_teacher_operation(save_questions)
            
            if success:
                st.success(f"{len(valid_questions)} perguntas carregadas e validadas com sucesso!")
            else:
                st.error("Erro ao salvar perguntas. Tente novamente.")
                
        except json.JSONDecodeError:
            st.error("Arquivo JSON inválido. Verifique a sintaxe do arquivo.")
        except Exception as e:
            st.error(f"Erro ao processar arquivo: {str(e)}")
    
    # Botão de voltar
    if st.button("Voltar ao Painel do Professor", key="back_to_dashboard_from_upload", use_container_width=True):
        navigate_to("teacher_dashboard")
        st.rerun()

def validate_question_structure(q_data, question_num):
    """Valida estrutura de uma pergunta"""
    if not isinstance(q_data, dict):
        st.error(f"Pergunta {question_num}: deve ser um objeto JSON.")
        return False
    
    required_fields = ["question", "options", "correct"]
    for field in required_fields:
        if field not in q_data:
            st.error(f"Pergunta {question_num}: campo '{field}' é obrigatório.")
            return False
    
    # Validar texto da pergunta
    if not isinstance(q_data["question"], str) or not q_data["question"].strip():
        st.error(f"Pergunta {question_num}: texto da pergunta deve ser uma string não vazia.")
        return False
    
    # Validar opções
    if not isinstance(q_data["options"], list) or len(q_data["options"]) != 4:
        st.error(f"Pergunta {question_num}: deve ter exatamente 4 opções.")
        return False
    
    for i, option in enumerate(q_data["options"]):
        if not isinstance(option, str) or not option.strip():
            st.error(f"Pergunta {question_num}, opção {i+1}: deve ser uma string não vazia.")
            return False
    
    # Validar resposta correta
    if not isinstance(q_data["correct"], int) or not (0 <= q_data["correct"] < 4):
        st.error(f"Pergunta {question_num}: resposta correta deve ser um número entre 0 e 3.")
        return False
    
    return True

def render_teacher_game_control():
    """Renderiza controle do jogo para professor"""
    current_game_code = st.session_state.get("game_code")
    if not current_game_code:
        st.error("Nenhum código de jogo encontrado na sessão.")
        navigate_to("teacher_dashboard")
        st.rerun()
        return
    
    def load_current_game():
        return Game.get_by_code(current_game_code)
    
    current_game = resilient_teacher_operation(load_current_game)
    if not current_game:
        st.error(f"Jogo com código {current_game_code} não encontrado!")
        navigate_to("teacher_dashboard")
        st.rerun()
        return
    
    st.markdown("<h1 class='title'>🎮 Controle do Jogo</h1>", unsafe_allow_html=True)
    
    # Botão voltar
    if st.button("Voltar ao painel", key="back_to_dashboard"):
        navigate_to("teacher_dashboard")
        st.rerun()
    
    # Ações do jogo
    render_game_control_actions(current_game)
    
    # Informações do jogo
    render_game_info(current_game)
    
    # Auto-refresh para jogos ativos
    if current_game and current_game.status in ["waiting", "active"]:
        time.sleep(3)
        st.rerun()

def render_game_control_actions(current_game):
    """Renderiza ações de controle do jogo"""
    col1, col2 = st.columns(2)
    
    with col1:
        if current_game.status == "waiting":
            can_start = len(current_game.players) > 0
            if st.button("Iniciar jogo", disabled=not can_start, use_container_width=True, type="primary"):
                start_game_operation(current_game)
        
        elif current_game.status == "active":
            if st.button("▶️ Próxima pergunta", use_container_width=True, type="primary"):
                next_question_operation(current_game)
    
    with col2:
        if current_game.status != "finished":
            if st.button("⏹️ Finalizar Jogo", use_container_width=True):
                finish_game_operation(current_game)
        else:
            if st.button("🏆 Ver Resultados Finais", use_container_width=True):
                navigate_to("game_results")
                st.rerun()

def start_game_operation(game):
    """Inicia o jogo"""
    def start_operation():
        game.start_game()
        return True
    
    with st.spinner("Iniciando jogo..."):
        success = resilient_teacher_operation(start_operation)
    
    if success:
        st.rerun()
    else:
        st.error("Erro ao iniciar jogo.")

def next_question_operation(game):
    """Avança para próxima pergunta"""
    def next_operation():
        return game.next_question()
    
    with st.spinner("Carregando próxima pergunta..."):
        proceed = resilient_teacher_operation(next_operation)
    
    if proceed is not None:
        if proceed:
            st.session_state.show_ranking = True
            st.rerun()
        else:
            navigate_to("game_results")
            st.rerun()
    else:
        st.error("Erro ao avançar pergunta.")

def finish_game_operation(game):
    """Finaliza o jogo"""
    def finish_operation():
        game.status = "finished"
        game.save()
        return True
    
    with st.spinner("Finalizando jogo..."):
        success = resilient_teacher_operation(finish_operation)
    
    if success:
        navigate_to("game_results")
        st.rerun()
    else:
        st.error("Erro ao finalizar jogo.")

def render_game_info(current_game):
    """Renderiza informações do jogo"""
    st.divider()
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.header(f"🔑 Código: `{current_game.code}`")
        st.caption(f"Status: {current_game.status.capitalize()}")
        
        if current_game.status == "waiting":
            render_waiting_players(current_game)
        elif current_game.status == "active":
            render_current_question(current_game)
        elif current_game.status == "finished":
            st.success("🎉 Jogo finalizado!")
            st.markdown("Os resultados finais podem ser visualizados na página de resultados.")
    
    with col2:
        render_current_ranking(current_game)

def render_waiting_players(game):
    """Renderiza lista de jogadores esperando"""
    st.subheader("Jogadores na sala:")
    
    if not game.players:
        st.info("Nenhum jogador entrou.")
    else:
        player_cols = st.columns(3)
        players_list = list(game.players.items())
        
        for i, (player_name, player_data) in enumerate(players_list):
            with player_cols[i % 3]:
                icon = player_data.get('icon', '❓') if isinstance(player_data, dict) else '❓'
                st.markdown(
                    f"<div style='text-align:center; padding:10px; margin:5px; "
                    f"background-color:#e0f7fa; border-radius:10px;'>"
                    f"<span style='font-size:2rem;'>{icon}</span><br>{player_name}</div>",
                    unsafe_allow_html=True
                )

def render_current_question(game):
    """Renderiza pergunta atual"""
    q_idx = game.current_question
    if 0 <= q_idx < len(game.questions):
        st.markdown(f"**Pergunta {q_idx + 1} de {len(game.questions)}:**")
        q_data = game.questions[q_idx]
        st.markdown(f"### {q_data['question']}")
        
        st.write("**Opções:**")
        for i, opt in enumerate(q_data["options"]):
            is_correct = i == q_data['correct']
            color = "color:green; font-weight:bold;" if is_correct else ""
            st.markdown(
                f"<span style='{color}'>{i+1}. {opt}{' (Correta)' if is_correct else ''}</span>",
                unsafe_allow_html=True
            )
        
        # Contador de respostas
        answered_count = sum(
            1 for player_data in game.players.values()
            if isinstance(player_data, dict) and
            any(ans.get('question') == q_idx for ans in player_data.get('answers', []))
        )
        st.info(f"{answered_count} de {len(game.players)} jogadores responderam.")
    else:
        st.warning("Índice da pergunta atual fora do intervalo. O jogo pode ter terminado.")

def render_current_ranking(game):
    """Renderiza ranking atual"""
    st.subheader("🏆 Ranking atual")
    
    def get_ranking():
        return game.get_ranking()
    
    ranking_data = resilient_teacher_operation(get_ranking) or []
    
    if not ranking_data:
        st.info("Nenhum jogador pontuou ainda.")
    else:
        for i, player_info in enumerate(ranking_data[:10]):
            medal = ["🥇", "🥈", "🥉"][i] if i < 3 else f"{i+1}."
            
            # Cores do ranking
            if i == 0:
                bg, border = '#FFFACD', '#FFD700'
            elif i == 1:
                bg, border = '#F0F8FF', '#ADD8E6'
            elif i == 2:
                bg, border = '#FFE4E1', '#FFB6C1'
            else:
                bg, border = '#f9f9f9', '#eee'
            
            icon = player_info.get('icon', '❓')
            name = player_info.get('name', 'Unknown')
            score = player_info.get('score', 0)
            
            st.markdown(
                f"""<div style='display:flex;align-items:center;padding:8px;margin-bottom:5px;
                background-color:{bg};border-radius:8px;border:1px solid {border};
                box-shadow:0 2px 4px rgba(0,0,0,0.05);'>
                <span style='font-weight:bold;margin-right:12px;font-size:1.1em;width:30px;text-align:center;'>{medal}</span>
                <span style='font-size:1.6rem;margin-right:10px;'>{icon}</span>
                <span style='flex-grow:1;font-weight:500;color:#333;'>{name}</span>
                <span style='font-weight:bold;color:#007bff;'>{score} pts</span>
                </div>""",
                unsafe_allow_html=True
            )