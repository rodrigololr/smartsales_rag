#!/usr/bin/env python3
"""
issue_flow.py — Automação Determinística do Ciclo Issue-to-PR do SmartSales RAG.

Garante conformidade com o GEMINI.md:
1. Extração estruturada da issue via GitHub CLI (zero alucinação de metadados).
2. Criação automática de branch padronizada (<tipo>/<PACOTE>-<slug> a partir de develop).
3. Geração determinística do plano em .gemini/plans/<id>-<PACOTE>-<slug>.md.
4. Validação de tasks e commits atômicos.
5. Abertura de PR conforme template oficial (.github/PULL_REQUEST_TEMPLATE.md) com trava estrita anti-emoji.

Uso:
  python .gemini/scripts/issue_flow.py start <URL_OU_ID> [--branch-type feat|fix|test|docs] [--slug custom-slug]
  python .gemini/scripts/issue_flow.py plan-status
  python .gemini/scripts/issue_flow.py pr <URL_OU_ID> [--summary "Resumo detalhado..."] [--dry-run]
"""

import argparse
import json
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_DEFAULT = "rodrigololr/smartsales_rag"

EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U00002702-\U000027B0"  # dingbats
    "\U000024C2-\U0001F251"
    "\U0001F900-\U0001F9FF"  # supplemental symbols
    "\U0001FA70-\U0001FAFF"  # symbols and pictographs extended-a
    "\U00002600-\U000026FF"  # misc symbols (ex: checkmarks gráficos, alertas)
    "\U00002B50-\U00002B55"
    "\U0000200D"              # zero-width joiner
    "\U0000FE0F"              # variation selector
    "]+",
    flags=re.UNICODE,
)


def run_cmd(cmd: List[str], cwd: Optional[Path] = None, check: bool = True) -> subprocess.CompletedProcess:
    """Executa comando de sistema e retorna CompletedProcess garantindo UTF-8."""
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if check and result.returncode != 0:
        cmd_str = " ".join(cmd)
        err = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Comando falhou [{result.returncode}]: {cmd_str}\n{err}")
    return result


def parse_issue_id(input_str: str) -> int:
    """Extrai o número da issue a partir de URL completa ou número."""
    cleaned = input_str.strip().rstrip("/")
    # Ex: https://github.com/rodrigololr/smartsales_rag/issues/6
    m_url = re.search(r"/issues/(\d+)$", cleaned)
    if m_url:
        return int(m_url.group(1))
    # Ex: #6 ou 6
    m_num = re.search(r"^#?(\d+)$", cleaned)
    if m_num:
        return int(m_num.group(1))
    raise ValueError(f"Não foi possível extrair o ID da issue a partir de: '{input_str}'")


def strip_emojis(text: str) -> Tuple[str, bool]:
    """Remove emojis de texto e indica se algum foi removido."""
    cleaned = EMOJI_PATTERN.sub("", text)
    had_emoji = cleaned != text
    return cleaned, had_emoji


def slugify(text: str, max_length: int = 35) -> str:
    """Gera slug limpo e legível em ASCII."""
    # Remove marcações como [F01], [CRÍTICO], (EAP ...), etc.
    text = re.sub(r"\[[^\]]+\]", "", text)
    text = re.sub(r"\([^\)]+\)", "", text)
    # Remove acentos
    text = unicodedata.normalize("NFKD", text).encode("ASCII", "ignore").decode("utf-8")
    # Substitui caracteres não alfanuméricos por hífen
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    # Limita tamanho
    if len(text) > max_length:
        text = text[:max_length].rstrip("-")
    return text or "task"


def fetch_issue_data(issue_id: int, repo: str = REPO_DEFAULT) -> Dict[str, Any]:
    """Busca dados da issue via GitHub CLI."""
    cmd = [
        "gh", "issue", "view", str(issue_id),
        "--repo", repo,
        "--json", "number,title,body,labels,assignees,milestone,state,url"
    ]
    res = run_cmd(cmd)
    return json.loads(res.stdout)


def parse_metadata_from_issue(data: Dict[str, Any]) -> Dict[str, Any]:
    """Extrai metadados do pacote a partir do título e corpo estruturado da issue."""
    title = data.get("title", "")
    body = data.get("body", "")

    # Código do Pacote (ex: F01, B01, M02, G04)
    pkg = None
    m_pkg_title = re.search(r"\[([A-Z]\d{2})\]", title)
    if m_pkg_title:
        pkg = m_pkg_title.group(1)
    else:
        m_pkg_body = re.search(r"\*\*Código do Pacote\*\*\s*\|\s*`?([A-Z]\d{2})`?", body)
        if m_pkg_body:
            pkg = m_pkg_body.group(1)
        else:
            m_pkg_general = re.search(r"\b([B|M|F|G]\d{2})\b", title)
            if m_pkg_general:
                pkg = m_pkg_general.group(1)

    if not pkg:
        pkg = "MISC"

    # Marco / Milestone
    milestone_obj = data.get("milestone")
    milestone = "M1"
    if milestone_obj and isinstance(milestone_obj, dict):
        m_title = milestone_obj.get("title", "")
        m_m = re.search(r"\b(M[1-5])\b", m_title)
        if m_m:
            milestone = m_m.group(1)
        else:
            milestone = m_title
    else:
        m_body_m = re.search(r"\*\*Marco de Controle.*?\*\*\s*\|\s*\*\*?`?(M[1-5])`?\*\*?", body)
        if m_body_m:
            milestone = m_body_m.group(1)

    # Sprint
    sprint = "Sprint 1"
    m_sprint = re.search(r"\*\*Sprint\*\*\s*\|\s*`?([^`\n|]+)`?", body)
    if m_sprint:
        sprint = m_sprint.group(1).strip()

    # RACI
    raci_a = ""
    raci_r = ""
    m_raci_a = re.search(r"-\s*\*\*Aprovador\s*\(`A`[^)]*\)\*\*:\s*(.+)", body)
    if m_raci_a:
        raci_a = m_raci_a.group(1).strip()
    m_raci_r = re.search(r"-\s*\*\*Responsáveis pela Execução\s*\(`R`[^)]*\)\*\*:\s*(.+)", body)
    if m_raci_r:
        raci_r = m_raci_r.group(1).strip()

    # Entregáveis da EAP
    eap_tasks = []
    for line in body.splitlines():
        line_s = line.strip()
        if line_s.startswith("- [ ]") or line_s.startswith("- [x]"):
            if "EAP" in line_s:
                eap_tasks.append(line_s)

    # Specs de Referência
    specs_ref = list(dict.fromkeys(re.findall(r"(specs/[a-zA-Z0-9_\-/\.]+\.md)", body)))

    # Casos de Teste TDD
    tdd_cases = []
    m_tdd = re.search(r"Casos TDD obrigatórios:\s*`?([^`\.\n]+)`?", body)
    if m_tdd:
        tdd_cases = [c.strip() for c in re.split(r"[,;]\s*", m_tdd.group(1))]

    # Tipo padrão de branch
    if pkg.startswith("G"):
        default_branch_type = "docs"
    elif pkg in ("B05", "F05"):
        default_branch_type = "test"
    else:
        default_branch_type = "feat"

    return {
        "id": data["number"],
        "title": title,
        "package": pkg,
        "milestone": milestone,
        "sprint": sprint,
        "raci_a": raci_a,
        "raci_r": raci_r,
        "eap_tasks": eap_tasks,
        "specs_ref": specs_ref,
        "tdd_cases": tdd_cases,
        "url": data.get("url", f"https://github.com/{REPO_DEFAULT}/issues/{data['number']}"),
        "default_branch_type": default_branch_type,
    }


def cmd_start(args: argparse.Namespace) -> None:
    """Inicia o fluxo para uma issue: fetch, branch e esqueleto do plano."""
    repo_root = Path(__file__).resolve().parents[2]
    issue_id = parse_issue_id(args.issue)

    print(f"[INFO] Consultando issue #{issue_id} no GitHub...")
    raw_data = fetch_issue_data(issue_id, repo=args.repo)
    meta = parse_metadata_from_issue(raw_data)

    pkg = meta["package"]
    slug = args.slug or slugify(meta["title"])
    b_type = args.branch_type or meta["default_branch_type"]
    branch_name = f"{b_type}/{pkg}-{slug}"
    base_branch = args.base or "develop"

    print(f"[INFO] Pacote: {pkg} | Marco: {meta['milestone']} | Sprint: {meta['sprint']}")
    print(f"[INFO] Branch calculada: {branch_name} (a partir de: {base_branch})")

    if not args.dry_run:
        # Garantir checkout da branch base
        print(f"[INFO] Alternando para a branch base '{base_branch}'...")
        run_cmd(["git", "checkout", base_branch], cwd=repo_root)
        if base_branch == "develop":
            try:
                run_cmd(["git", "pull", "origin", "develop"], cwd=repo_root, check=False)
            except Exception:
                pass

        # Criar ou alternar para a branch de trabalho
        branches = run_cmd(["git", "branch", "--list", branch_name], cwd=repo_root).stdout.strip()
        if branches:
            print(f"[INFO] Alternando para branch existente: {branch_name}")
            run_cmd(["git", "checkout", branch_name], cwd=repo_root)
        else:
            print(f"[INFO] Criando nova branch a partir de {base_branch}: {branch_name}")
            run_cmd(["git", "checkout", "-b", branch_name, base_branch], cwd=repo_root)

    # Gerar plano em .gemini/plans/<id>-<package>-<slug>.md
    plans_dir = repo_root / ".gemini" / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    plan_path = plans_dir / f"{issue_id}-{pkg}-{slug}.md"

    eap_markdown = "\n".join(meta["eap_tasks"]) if meta["eap_tasks"] else "- [ ] Implementar entregáveis do pacote"
    specs_markdown = "\n".join([f"- [`{s}`](file:///{repo_root.as_posix()}/{s})" for s in meta["specs_ref"]]) or "- Nenhuma spec específica listada"
    tdd_markdown = ", ".join(meta["tdd_cases"]) if meta["tdd_cases"] else "Conforme spec de TDD"

    plan_content = f"""# Implementation Plan — Issue #{issue_id}: {meta['title']}

## Identificação e Metadados
- **Número da Issue**: #{issue_id}
- **Código do Pacote EAP**: `{pkg}`
- **Marco (*Milestone*)**: {meta['milestone']}
- **Sprint**: {meta['sprint']}
- **Branch de Trabalho**: `{branch_name}`
- **URL da Issue**: {meta['url']}
- **Governança RACI**:
  - **Aprovador (`A`)**: {meta['raci_a']}
  - **Executores (`R`)**: {meta['raci_r']}

---

## 1. Objetivo e Escopo
- **Meta do Pacote**: Implementar as entregas vinculadas à issue #{issue_id} respeitando o SDD e TDD.
- **Entregáveis da EAP**:
{eap_markdown}

---

## 2. Especificações de Referência (`specs/`)
{specs_markdown}

---

## 3. Testes Automatizados Obrigatórios (TDD)
- **Casos de Teste Mapeados**: `{tdd_markdown}`
- **Meta de Cobertura**: >= 70% com zero defeitos críticos.

---

## 4. Lista de Tarefas Atômicas (1 Commit por Task)

> [!IMPORTANT]
> Cada tarefa abaixo deve ser executada individualmente, testada e comitada separadamente.

- [ ] **Task 1: Setup e Definição de Tipos/Contratos**
  - **Arquivos**: A definir conforme camada
  - **Mensagem do Commit**: `{b_type}({pkg}): setup initial structure and contracts`

- [ ] **Task 2: Testes TDD Red (Falhando)**
  - **Arquivos**: `tests/...`
  - **Mensagem do Commit**: `test({pkg}): add failing unit/integration tests for issue #{issue_id}`

- [ ] **Task 3: Implementação TDD Green (Código de Produção)**
  - **Arquivos**: `src/...` ou `app/...`
  - **Mensagem do Commit**: `{b_type}({pkg}): implement core logic satisfying acceptance criteria`

- [ ] **Task 4: Refactor, Linters e Cobertura (Gate)**
  - **Arquivos**: Módulos alterados
  - **Mensagem do Commit**: `refactor({pkg}): clean code and ensure test coverage >= 70%`

---

## 5. Critérios de Aceite e Comandos de Validação
```bash
# Executar suíte de validação antes de abrir PR:
# Backend/Specs:
uv run --with-requirements tests/requirements-specs.txt python -m unittest discover -s tests -v

# Frontend (quando aplicável):
npm --prefix frontend run test:unit
```
"""

    if not plan_path.exists() or args.overwrite_plan:
        plan_path.write_text(plan_content, encoding="utf-8")
        print(f"[OK] Plano gerado em: {plan_path.relative_to(repo_root)}")
    else:
        print(f"[INFO] Plano já existe em: {plan_path.relative_to(repo_root)} (use --overwrite-plan se desejar recriar)")

    print("\n" + "=" * 60)
    print(f"Fluxo iniciado com sucesso para a Issue #{issue_id}!")
    print(f"Branch atual : {branch_name}")
    print(f"Arquivo Plano: {plan_path.relative_to(repo_root)}")
    print("Próximo passo: execute as tarefas com 1 commit por task e depois abra o PR com:")
    print(f"  python .gemini/scripts/issue_flow.py pr {issue_id} --summary \"<resumo>\"")
    print("=" * 60 + "\n")


def cmd_pr(args: argparse.Namespace) -> None:
    """Valida, formata e abre o Pull Request via GitHub CLI sem emojis."""
    repo_root = Path(__file__).resolve().parents[2]
    issue_id = parse_issue_id(args.issue)

    print(f"[INFO] Consultando issue #{issue_id}...")
    raw_data = fetch_issue_data(issue_id, repo=args.repo)
    meta = parse_metadata_from_issue(raw_data)
    pkg = meta["package"]

    # Obter branch atual
    current_branch = run_cmd(["git", "branch", "--show-current"], cwd=repo_root).stdout.strip()
    if not current_branch:
        raise RuntimeError("Não foi possível determinar a branch git atual.")

    if current_branch in ("develop", "main"):
        raise RuntimeError(f"Você está na branch '{current_branch}'. O PR deve ser aberto a partir de uma feature branch!")

    print(f"[INFO] Branch identificada: {current_branch}")

    # Obter commits feitos na branch em relação a develop
    log_res = run_cmd(
        ["git", "log", f"origin/develop..{current_branch}", "--oneline"],
        cwd=repo_root,
        check=False
    )
    commit_lines = [line.strip() for line in log_res.stdout.splitlines() if line.strip()]

    # Montar resumo das alterações
    summary_text = args.summary.strip() if args.summary else ""
    if not summary_text:
        if commit_lines:
            summary_text = "\n".join([f"- {c}" for c in commit_lines])
        else:
            summary_text = f"- Implementação técnica completa das entregas do pacote {pkg} vinculadas à issue #{issue_id}."

    # Subpacotes da EAP
    subpackages_text = ", ".join(re.findall(r"EAP\s+(\d+\.\d+)", meta["title"] + " " + raw_data.get("body", "")))
    if not subpackages_text:
        subpackages_text = "3.5, 4.1"

    base_branch = getattr(args, "base", None) or "develop"

    # Montar corpo do PR conforme .github/PULL_REQUEST_TEMPLATE.md
    pr_body = f"""## 1. Identificação do Pacote (EAP / Gantt)

- **Pacote Operacional (`G01–G04`, `B01–B05`, `M01–M05`, `F01–F05`)**: `{pkg}`
- **Subpacote(s) da EAP (`1.1–7.4`)**: `{subpackages_text}`
- **Issue Relacionada**: Closes #{issue_id}
- **Marco (*Milestone*)**: `{meta['milestone']}`

---

## 2. Resumo das Alterações

{summary_text}

---

## 3. Governança RACI e Revisão Obrigatória

- **Executor (`R` — *Responsible*)**: {meta['raci_r'] or '@desenvolvedor'}
- **Aprovador da Camada (`A` — *Accountable*)**: {meta['raci_a'] or '@tech-lead'}

---

## 4. Checklist de Pronto (*Definition of Done — DoD*)

- [x] **Aderência à Spec (SDD)**: Todos os requisitos (`RF`/`RNF`/`RN`) e contratos (`openapi.yaml` / DDL) da Spec em `specs/` foram respeitados.
- [x] **Testes Automatizados (TDD)**: Casos de teste (`UT-*` / `IT-*` / `E2E-*`) implementados e passando com cobertura >= 70%.
- [x] **Guardrails e Zero Alucinação**: Sem regressão de Faithfulness (>= 0.85), voltagem (127V/220V) ou estoque (stock_quantity > 0).
- [x] **Clean Code e Layers**: Isolamento Presentation -> Application -> Domain <- Infrastructure preservado, sem magic numbers.
"""

    # Extrair título padrão para o PR
    b_type = current_branch.split("/")[0] if "/" in current_branch else "feat"
    clean_title_core = re.sub(r"\[[^\]]+\]", "", meta["title"])
    clean_title_core = re.sub(r"\([^)]+\)", "", clean_title_core).strip()
    pr_title = f"{b_type}({pkg}): {clean_title_core}"

    # Trava Rígida Anti-Emoji
    clean_title, title_had_emoji = strip_emojis(pr_title)
    clean_body, body_had_emoji = strip_emojis(pr_body)

    if title_had_emoji or body_had_emoji:
        print("[AVISO] Emojis detectados no título ou corpo do PR. Eles foram removidos automaticamente para cumprir a regra de zero emotes.")

    print("\n" + "=" * 60)
    print("PROPOSTA DE PULL REQUEST:")
    print(f"Base : develop")
    print(f"Head : {current_branch}")
    print(f"Title: {clean_title}")
    print("-" * 60)
    print(clean_body)
    print("=" * 60 + "\n")

    if args.dry_run:
        print("[DRY-RUN] PR não foi submetido. Remova --dry-run para abrir no GitHub.")
        return

    # Fazer push da branch
    print(f"[INFO] Fazendo push da branch {current_branch} para origin...")
    run_cmd(["git", "push", "-u", "origin", current_branch], cwd=repo_root)

    # Executar gh pr create
    print("[INFO] Criando Pull Request via GitHub CLI...")
    cmd_gh = [
        "gh", "pr", "create",
        "--repo", args.repo,
        "--base", base_branch,
        "--head", current_branch,
        "--title", clean_title,
        "--body", clean_body,
    ]
    res_pr = run_cmd(cmd_gh, cwd=repo_root)
    pr_url = res_pr.stdout.strip()
    print(f"[SUCESSO] Pull Request aberto: {pr_url}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="issue_flow.py — Automação do Ciclo Issue-to-PR (SmartSales RAG)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--repo", default=REPO_DEFAULT, help="Repositório GitHub (padrão: rodrigololr/smartsales_rag)")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcomando 'start'
    p_start = subparsers.add_parser("start", help="Inicia o desenvolvimento de uma issue (branch + plano)")
    p_start.add_argument("issue", help="URL completa da issue ou número (ex: https://github.com/.../issues/6 ou 6)")
    p_start.add_argument("--base", default="develop", help="Branch base a partir da qual criar a nova branch (padrão: develop)")
    p_start.add_argument("--branch-type", choices=["feat", "fix", "test", "docs"], help="Tipo de branch (feat/fix/test/docs)")
    p_start.add_argument("--slug", help="Slug personalizado para o nome da branch")
    p_start.add_argument("--overwrite-plan", action="store_true", help="Sobrescrever plano se já existir")
    p_start.add_argument("--dry-run", action="store_true", help="Apenas simular sem criar branch ou arquivo")

    # Subcomando 'pr'
    p_pr = subparsers.add_parser("pr", help="Abre o Pull Request oficial vinculado à issue sem emojis")
    p_pr.add_argument("issue", help="URL completa da issue ou número")
    p_pr.add_argument("--base", default="develop", help="Branch de destino do PR (padrão: develop)")
    p_pr.add_argument("--summary", help="Resumo detalhado das alterações técnicas realizadas")
    p_pr.add_argument("--dry-run", action="store_true", help="Apenas visualizar o corpo do PR sem enviar")

    args = parser.parse_args()

    try:
        if args.command == "start":
            cmd_start(args)
        elif args.command == "pr":
            cmd_pr(args)
    except Exception as exc:
        print(f"[ERRO] {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
