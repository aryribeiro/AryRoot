Obs.: caso o app esteja no modo "sleeping" (dormindo) ao entrar, basta clicar no botão que estará disponível e aguardar, para ativar o mesmo. 
![print](https://github.com/user-attachments/assets/342a211c-30f1-47c2-8a72-d32c4c29d4a4)

# 🎮 AryRoot - Quiz Game Multiplayer

O AryRoot é um web app interativo de quiz multiplayer, construído em Python com Streamlit. Ele permite que professores criem e gerenciem jogos de perguntas e respostas, e que alunos participem em tempo real.

## Funcionalidades Principais

* **Para Professores:**
    * Login seguro com nome de usuário, senha e verificação captcha.
    * Criação de conta de professor (funcionalidade de administrador para o usuário "professor" padrão).
    * Dashboard para gerenciamento de jogos e perguntas.
    * Criação de novos jogos com um conjunto de perguntas personalizadas.
    * Gerenciamento de perguntas:
        * Adicionar, editar e remover perguntas manualmente.
        * Carregar perguntas a partir de um arquivo JSON.
    * Controle do jogo em tempo real:
        * Iniciar o jogo.
        * Avançar para a próxima pergunta.
        * Visualizar jogadores na sala de espera.
        * Visualizar ranking parcial durante o jogo.
        * Finalizar o jogo.
    * Visualização dos resultados finais e ranking completo.
    * (Admin) Gerenciamento de outras contas de professores (criar, editar, remover).

* **Para Alunos:**
    * Entrar em um jogo existente usando um código de jogo fornecido pelo professor.
    * Escolher um apelido e um ícone/emoji.
    * Sala de espera interativa aguardando o início do jogo.
    * Responder perguntas de múltipla escolha.
    * Pontuação baseada na correção e no tempo de resposta.
    * Visualização de feedback imediato (correto/incorreto).
    * Visualização de ranking parcial entre as perguntas.
    * Visualização dos resultados finais, pódio e ranking completo.
    * Efeitos sonoros e visuais (balões para o vencedor).

## Estrutura do Projeto

* `app.py`: Ponto de entrada principal do aplicativo Streamlit, roteamento de páginas e estilos globais.
* `core.py`: Contém a lógica de negócios principal, incluindo as classes `Game` e `Teacher`, gerenciamento de dados (leitura/escrita em JSON), geração de códigos, e as otimizações de cache em memória e locks de escrita.
* `aluno.py`: Define a interface e o fluxo do usuário para os alunos.
* `professor.py`: Define a interface e o fluxo do usuário para os professores, incluindo funcionalidades administrativas.
* `data/`: Diretório onde os arquivos `games.json` e `teachers.json` são armazenados (criado automaticamente).
* `static/`: Diretório para arquivos estáticos, como o `aplausos.mp3` e `silent.mp3`.
* `.env`: Arquivo para configurar variáveis de ambiente (ex: senha do professor administrador).

## Tecnologias Utilizadas

* **Python:** Linguagem de programação principal.
* **Streamlit:** Framework para construção da interface web.
* **bcrypt:** Para hashing seguro de senhas.
* **python-dotenv:** Para gerenciamento de variáveis de ambiente.

## Otimizações Implementadas

1.  **Cache de Leitura em Memória:** As instâncias dos jogos (`Game`) e professores (`Teacher`) são mantidas em um cache em memória para reduzir as leituras repetitivas dos arquivos JSON, melhorando a performance e a responsividade do aplicativo.
2.  **Serialização de Gravações com `threading.Lock`:** As operações de escrita nos arquivos `games.json` e `teachers.json` são protegidas por locks. Isso garante que apenas uma operação de escrita ocorra por vez em cada arquivo, prevenindo corrupção de dados e condições de corrida em ambientes com múltiplos acessos.

## Como Executar Localmente

1.  **Clone o repositório (se aplicável) ou tenha os arquivos em um diretório.**

2.  **Crie e ative um ambiente virtual (recomendado):**
    ```bash
    python -m venv venv
    # No Windows
    venv\Scripts\activate
    # No macOS/Linux
    source venv/bin/activate
    ```

3.  **Instale as dependências:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Crie um arquivo `.env` na raiz do projeto:**
    Este arquivo é usado para configurar a senha do professor "demo" inicial. Adicione a seguinte linha, substituindo `"sua_senha_segura_aqui"` por uma senha de sua escolha:
    ```env
    DEMO_PROFESSOR_PASSWORD="sua_senha_segura_aqui"
    DEMO_PROFESSOR_NAME="Professor Demo"
    DEMO_PROFESSOR_EMAIL="professor@exemplo.com"
    ```
    Se este arquivo ou a variável `DEMO_PROFESSOR_PASSWORD` não for definida, o usuário "professor" não poderá logar até que uma conta seja criada manualmente ou o arquivo `data/teachers.json` seja ajustado.

5.  **Crie o diretório `static` na raiz do projeto e adicione os arquivos de áudio:**
    * `static/aplausos.mp3` (som de aplausos para o final do jogo)

6.  **Execute o aplicativo Streamlit:**
    ```bash
    streamlit run app.py
    ```

7.  Abra seu navegador e acesse o endereço fornecido (geralmente `http://localhost:8501`).

## Próximos Passos Potenciais (Melhorias Futuras)

* **Migração para Banco de Dados (SQLite/PostgreSQL):** Para melhor escalabilidade, concorrência e gerenciamento de dados, substituir os arquivos JSON por um sistema de banco de dados.
* **Refinamento da Interface do Usuário (UX):** Melhorias contínuas na usabilidade e design.
* **Testes Automatizados:** Implementação de testes unitários e de integração.
* **Sistema de Fila de Gravação Mais Robusto:** Se a contenção de escrita ainda for um problema, explorar filas de mensagens externas (Redis, RabbitMQ) para gravações assíncronas e persistentes.

---
Autor: Ary Ribeiro
Contato: aryribeiro@gmail.com
LinkedIn: https://www.linkedin.com/in/aryribeiro
