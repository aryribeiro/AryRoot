Obs.: caso o app esteja no modo "sleeping" (dormindo) ao entrar, basta clicar no botão que estará disponível e aguardar, para ativar o mesmo. 
<img width="700" height="515" alt="image" src="https://github.com/user-attachments/assets/732132be-7f6b-497c-b2db-e235cd8de4b9" />

O AryRoot é um web app interativo de quiz multiplayer estilo Kahoot, construído em Python com Streamlit. Ele permite que professores criem e gerenciem jogos de perguntas e respostas, e que alunos participem em tempo real com pontuação baseada em velocidade e streaks.

## Funcionalidades Principais

* **Para Professores:**
    * Login seguro com nome de usuário, senha e verificação captcha (matemática simples).
    * Criação de conta de professor (funcionalidade de administrador para o usuário "professor" padrão).
    * Dashboard para gerenciamento de jogos e perguntas.
    * Criação de novos jogos com um conjunto de perguntas personalizadas.
    * Gerenciamento de perguntas:
        * Adicionar, editar e remover perguntas manualmente.
        * Carregar perguntas a partir de um arquivo JSON.
    * Controle do jogo em tempo real:
        * Iniciar o jogo com tempo configurável por pergunta (20s, 60s ou 90s).
        * Avançar para a próxima pergunta.
        * Visualizar jogadores na sala de espera.
        * Ranking parcial em sidebar fixo (sempre visível, sem opção de fechar).
        * Finalizar o jogo.
        * Timer sincronizado com o servidor (anti-trapaça).
    * Visualização dos resultados finais e ranking completo.
    * (Admin) Gerenciamento de outras contas de professores (criar, editar, remover).

* **Para Alunos:**
    * Entrar em um jogo existente usando um código de jogo fornecido pelo professor.
    * Escolher um apelido e um ícone/emoji (grid de 90 emojis em 5 colunas, responsivo mobile/desktop).
    * Reconexão automática após F5/reload via query params (`gc` e `pn` persistidos na URL).
    * Sala de espera interativa aguardando o início do jogo.
    * Responder perguntas de múltipla escolha com botões coloridos estilo Kahoot (▲ vermelho, ◆ azul, ● amarelo, ■ verde).
    * Timer sincronizado com o servidor (não reinicia com F5 — anti-trapaça).
    * Pontuação estilo Kahoot: base 1000 pontos com time decay + streak bonus (+100 por acerto consecutivo, cap 500).
    * Zero pontos se tempo do servidor expirar, mesmo acertando.
    * Feedback imediato (correto/incorreto com pontos e streak).
    * Visualização de ranking parcial entre as perguntas.
    * Visualização dos resultados finais, pódio e ranking completo.
    * Efeitos sonoros e visuais (balões para o vencedor).
    * Trilha sonora de fundo (som.mp3) com autoplay após primeiro clique.

## Sistema de Pontuação (Kahoot-style)

* **Fórmula base:** `pontos = 1000 * (1 - (tempo_resposta / tempo_limite) / 2)` — mínimo 500 pontos.
* **Streak bonus:** `min((streak - 1) * 100, 500)` — acertos consecutivos bonificam.
* **Tempo expirado:** Zero pontos, independente de acertar.
* **Timer centralizado no servidor:** `question_start_time` é definido pelo professor; o aluno não controla o tempo.

## Anti-Trapaça

* O tempo é calculado no servidor via `question_start_time` (não no cliente).
* F5 no aluno não reinicia o timer — o tempo real é `datetime.now() - question_start_time`.
* Se o tempo do servidor já expirou, o aluno é bloqueado de responder.
* Deduplicação de respostas (previne double-click).

## Estrutura do Projeto

* `app.py`: Ponto de entrada principal, roteamento, estilos CSS globais, meta theme-color, trilha sonora e scrollbar customizada.
* `core.py`: Lógica de negócios — classes `Game` e `Teacher`, SQLite com connection pool, circuit breaker, distributed locks, scoring Kahoot.
* `aluno.py`: Interface do aluno — home, seleção de emoji, sala de espera, game, resultados.
* `professor.py`: Interface do professor — login, dashboard, controle do jogo, ranking sidebar.
* `data/`: Diretório do banco SQLite (criado automaticamente).
* `static/`: Arquivos estáticos — `logo.png`, `som.mp3`, `aplausos.mp3`, `silent.mp3`.
* `.streamlit/config.toml`: Configuração do Streamlit (static serving habilitado).

## Tecnologias Utilizadas

* **Python 3.x** — Linguagem principal.
* **Streamlit** — Framework web com componentes reativos.
* **SQLite** — Banco de dados com connection pool e circuit breaker.
* **bcrypt** — Hashing seguro de senhas.
* **python-dotenv** — Gerenciamento de variáveis de ambiente.
* **JavaScript/CSS injetados** — Timer em tempo real (requestAnimationFrame), botões Kahoot coloridos, scrollbar customizada, theme-color mobile.

## Otimizações e Padrões

1. **Cache em memória + SQLite:** Instâncias de `Game` em cache com TTL, SQLite como persistência.
2. **Distributed Locks:** Operações críticas (responder, avançar pergunta) protegidas por locks nomeados.
3. **Circuit Breaker:** Proteção contra falhas cascata no acesso ao banco.
4. **Deduplicação:** Cache de operações para prevenir registros duplicados.
5. **Retry com backoff:** Operações de banco com retry exponencial.
6. **CSS responsivo mobile:** `key=` em containers + CSS `.st-key-{nome}` para impedir stacking de colunas no mobile (breakpoint 640px).
7. **MutationObserver:** Reaplica estilos em botões Kahoot após rerenders do Streamlit.

## Como Executar Localmente

1. **Clone o repositório:**
    ```bash
    git clone https://github.com/aryribeiro/AryRoot.git
    cd AryRoot
    ```

2. **Crie e ative um ambiente virtual (recomendado):**
    ```bash
    python -m venv venv
    # No Windows
    venv\Scripts\activate
    # No macOS/Linux
    source venv/bin/activate
    ```

3. **Instale as dependências:**
    ```bash
    pip install -r requirements.txt
    ```

4. **Crie um arquivo `.env` na raiz do projeto:**
    ```env
    DEMO_PROFESSOR_PASSWORD="sua_senha_segura_aqui"
    DEMO_PROFESSOR_NAME="Professor Demo"
    DEMO_PROFESSOR_EMAIL="professor@exemplo.com"
    ```

5. **Execute o aplicativo Streamlit:**
    ```bash
    streamlit run app.py
    ```

6. Abra seu navegador e acesse `http://localhost:8501`.

## Deploy

* **Plataforma:** Streamlit Community Cloud, auto-deploy a partir do branch `master`.
* **Secrets:** Configurados no dashboard do Streamlit Cloud (`st.secrets`).
* **Static files:** Servidos via `/app/static/` com `enableStaticServing = true`.

---
Autor: Ary Ribeiro
Contato: aryribeiro@gmail.com
LinkedIn: https://www.linkedin.com/in/aryribeiro
