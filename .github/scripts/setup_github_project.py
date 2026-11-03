#!/usr/bin/env python3
"""
Configura automaticamente o GitHub Project V2 do SmartSales RAG (Kanban + Roadmap/Gantt + Tabela RACI/CPM).
Requer escopo 'project' no GitHub CLI:
  gh auth refresh -h github.com -s project,read:project
"""
import json
import subprocess
import sys

OWNER = "rodrigololr"
REPO = "smartsales_rag"
PROJECT_TITLE = "SmartSales RAG — Kanban, Cronograma (Gantt) & Matriz RACI"

ITEMS_METADATA = {
    "[G01]": {
        "status": "Done",
        "sprint": "Sprint 1 (22/09–02/10)",
        "layer": "Gerência & PM",
        "cpm": "Folga Normal (> 1d)",
        "start": "2026-09-22",
        "end": "2026-09-29",
        "duration": 6,
        "float": "31d",
        "raci_a": "Antônio Rodrigo / Walber",
        "raci_r": "Walber, Antônio Rodrigo, Filipe, Pablo, Victor Hugo",
    },
    "[G03]": {
        "status": "Done",
        "sprint": "Sprint 1 (22/09–02/10)",
        "layer": "Gerência & PM",
        "cpm": "Folga Normal (> 1d)",
        "start": "2026-09-30",
        "end": "2026-10-02",
        "duration": 3,
        "float": "31d",
        "raci_a": "Antônio Rodrigo / Walber",
        "raci_r": "Walber, Antônio Rodrigo",
    },
    "[B01]": {
        "status": "In Progress",
        "sprint": "Sprint 1 (22/09–02/10)",
        "layer": "Backend & IA (RAG)",
        "cpm": "CRÍTICO (Folga 0d)",
        "start": "2026-09-22",
        "end": "2026-10-02",
        "duration": 9,
        "float": "0d (Crítico)",
        "raci_a": "Filipe (Tech Lead)",
        "raci_r": "Diogo, Filipe, Pablo, Eduardo",
    },
    "[M01]": {
        "status": "In Progress",
        "sprint": "Sprint 1 (22/09–02/10)",
        "layer": "Middle-end & Gateway",
        "cpm": "Quase Crítico (Folga 1d)",
        "start": "2026-09-22",
        "end": "2026-10-01",
        "duration": 8,
        "float": "1d (Quase Crítico)",
        "raci_a": "Pablo",
        "raci_r": "Well, Pablo",
    },
    "[F01]": {
        "status": "In Progress",
        "sprint": "Sprint 1 (22/09–02/10)",
        "layer": "Frontend & UX",
        "cpm": "Folga Normal (> 1d)",
        "start": "2026-09-22",
        "end": "2026-10-01",
        "duration": 8,
        "float": "3d",
        "raci_a": "Victor Hugo",
        "raci_r": "Eduardo, Victor Hugo",
    },
    "[B02]": {
        "status": "Todo",
        "sprint": "Sprint 2 (05/10–16/10)",
        "layer": "Backend & IA (RAG)",
        "cpm": "CRÍTICO (Folga 0d)",
        "start": "2026-10-05",
        "end": "2026-10-16",
        "duration": 8,
        "float": "0d (Crítico)",
        "raci_a": "Filipe (Tech Lead)",
        "raci_r": "Diogo, Filipe",
    },
    "[M02]": {
        "status": "Todo",
        "sprint": "Sprint 2 (05/10–16/10)",
        "layer": "Middle-end & Gateway",
        "cpm": "Quase Crítico (Folga 1d)",
        "start": "2026-10-05",
        "end": "2026-10-16",
        "duration": 8,
        "float": "1d (Quase Crítico)",
        "raci_a": "Pablo / Well",
        "raci_r": "Well, Pablo",
    },
    "[F02]": {
        "status": "Todo",
        "sprint": "Sprint 2 (05/10–16/10)",
        "layer": "Frontend & UX",
        "cpm": "Folga Normal (> 1d)",
        "start": "2026-10-02",
        "end": "2026-10-13",
        "duration": 7,
        "float": "3d",
        "raci_a": "Eduardo",
        "raci_r": "Victor Hugo, Eduardo",
    },
    "[B03]": {
        "status": "Todo",
        "sprint": "Sprint 3 (19/10–30/10)",
        "layer": "Backend & IA (RAG)",
        "cpm": "CRÍTICO (Folga 0d)",
        "start": "2026-10-19",
        "end": "2026-10-29",
        "duration": 8,
        "float": "0d (Crítico)",
        "raci_a": "Diogo / Filipe",
        "raci_r": "Filipe, Diogo",
    },
    "[M03]": {
        "status": "Todo",
        "sprint": "Sprint 3 (19/10–30/10)",
        "layer": "Middle-end & Gateway",
        "cpm": "Quase Crítico (Folga 1d)",
        "start": "2026-10-19",
        "end": "2026-10-27",
        "duration": 7,
        "float": "1d (Quase Crítico)",
        "raci_a": "Well",
        "raci_r": "Pablo, Well",
    },
    "[F03]": {
        "status": "Todo",
        "sprint": "Sprint 3 (19/10–30/10)",
        "layer": "Frontend & UX",
        "cpm": "Folga Normal (> 1d)",
        "start": "2026-10-14",
        "end": "2026-10-23",
        "duration": 7,
        "float": "3d",
        "raci_a": "Victor Hugo",
        "raci_r": "Eduardo, Victor Hugo",
    },
    "[B04]": {
        "status": "Todo",
        "sprint": "Sprint 4 (03/11–13/11)",
        "layer": "Backend & IA (RAG)",
        "cpm": "CRÍTICO (Folga 0d)",
        "start": "2026-10-30",
        "end": "2026-11-10",
        "duration": 7,
        "float": "0d (Crítico)",
        "raci_a": "Diogo",
        "raci_r": "Filipe, Diogo",
    },
    "[B05]": {
        "status": "Todo",
        "sprint": "Sprint 4 (03/11–13/11)",
        "layer": "QA & Homologação",
        "cpm": "Folga Normal (> 1d)",
        "start": "2026-10-30",
        "end": "2026-11-06",
        "duration": 5,
        "float": "7d",
        "raci_a": "Filipe (Tech Lead)",
        "raci_r": "Diogo, Victor Hugo, Filipe",
    },
    "[M04]": {
        "status": "Todo",
        "sprint": "Sprint 4 (03/11–13/11)",
        "layer": "Middle-end & Gateway",
        "cpm": "Quase Crítico (Folga 1d)",
        "start": "2026-10-29",
        "end": "2026-11-09",
        "duration": 7,
        "float": "1d (Quase Crítico)",
        "raci_a": "Well",
        "raci_r": "Pablo, Well",
    },
    "[M05]": {
        "status": "Todo",
        "sprint": "Sprint 4 (03/11–13/11)",
        "layer": "Middle-end & Gateway",
        "cpm": "Folga Normal (> 1d)",
        "start": "2026-10-29",
        "end": "2026-11-05",
        "duration": 5,
        "float": "3d",
        "raci_a": "Pablo",
        "raci_r": "Well, Pablo",
    },
    "[F04]": {
        "status": "Todo",
        "sprint": "Sprint 4 (03/11–13/11)",
        "layer": "Frontend & UX",
        "cpm": "Quase Crítico (Folga 1d)",
        "start": "2026-10-29",
        "end": "2026-11-09",
        "duration": 7,
        "float": "1d (Quase Crítico)",
        "raci_a": "Victor Hugo",
        "raci_r": "Eduardo, Victor Hugo",
    },
    "[G04]": {
        "status": "Todo",
        "sprint": "Sprint 4 (03/11–13/11)",
        "layer": "Gerência & PM",
        "cpm": "Folga Normal (> 1d)",
        "start": "2026-11-11",
        "end": "2026-11-13",
        "duration": 3,
        "float": "2d",
        "raci_a": "Filipe (Tech Lead)",
        "raci_r": "Diogo, Pablo, Eduardo, Antônio Rodrigo",
    },
    "[F05]": {
        "status": "Todo",
        "sprint": "Homologação & M5 (16/11–24/11)",
        "layer": "QA & Homologação",
        "cpm": "CRÍTICO (Folga 0d)",
        "start": "2026-11-11",
        "end": "2026-11-17",
        "duration": 5,
        "float": "0d (Crítico)",
        "raci_a": "Victor Hugo / Well / Filipe",
        "raci_r": "Victor Hugo, Well, Eduardo, Filipe, Diogo, Pablo",
    },
    "[G02]": {
        "status": "Todo",
        "sprint": "Homologação & M5 (16/11–24/11)",
        "layer": "Gerência & PM",
        "cpm": "CRÍTICO (Folga 0d)",
        "start": "2026-11-18",
        "end": "2026-11-23",
        "duration": 3,
        "float": "0d (Crítico)",
        "raci_a": "Walber / Antônio Rodrigo",
        "raci_r": "Todos os 8 integrantes",
    },
    "[RES": {
        "status": "In Progress",
        "sprint": "Homologação & M5 (16/11–24/11)",
        "layer": "Gerência & PM",
        "cpm": "CRÍTICO (Folga 0d)",
        "start": "2026-09-22",
        "end": "2026-11-24",
        "duration": 41,
        "float": "Pulmão +1d (24/11)",
        "raci_a": "Antônio Rodrigo (GP/SM)",
        "raci_r": "Walber (PO), Antônio Rodrigo (GP)",
    },
}


def graphql(query, variables=None):
    payload = {"query": query, "variables": variables or {}}
    proc = subprocess.run(
        ["gh", "api", "graphql", "--input", "-"],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        print(f"GraphQL error: {proc.stderr}", file=sys.stderr)
        sys.exit(1)
    data = json.loads(proc.stdout)
    if "errors" in data:
        print(f"GraphQL errors: {json.dumps(data['errors'], indent=2)}", file=sys.stderr)
        sys.exit(1)
    return data["data"]


def main():
    info = graphql(
        """
        query($owner: String!, $repo: String!) {
          user(login: $owner) {
            id
            projectsV2(first: 20) { nodes { id number title url } }
          }
          repository(owner: $owner, name: $repo) {
            id
            issues(first: 50, orderBy: {field: CREATED_AT, direction: ASC}) {
              nodes { id number title }
            }
          }
        }
        """,
        {"owner": OWNER, "repo": REPO},
    )

    user_id = info["user"]["id"]
    repo_id = info["repository"]["id"]
    issues = info["repository"]["issues"]["nodes"]

    project = next((p for p in info["user"]["projectsV2"]["nodes"] if p["title"] == PROJECT_TITLE), None)
    if not project:
        res = graphql(
            """
            mutation($ownerId: ID!, $title: String!) {
              createProjectV2(input: {ownerId: $ownerId, title: $title}) {
                projectV2 { id number title url }
              }
            }
            """,
            {"ownerId": user_id, "title": PROJECT_TITLE},
        )
        project = res["createProjectV2"]["projectV2"]
        print(f"Created Project #{project['number']}: {project['url']}")
    else:
        print(f"Using existing Project #{project['number']}: {project['url']}")

    project_id = project["id"]

    # Link project to repository and make it public
    graphql(
        """
        mutation($projectId: ID!, $repoId: ID!) {
          linkProjectV2ToRepository(input: {projectId: $projectId, repositoryId: $repoId}) {
            repository { id }
          }
          updateProjectV2(input: {
            projectId: $projectId,
            public: true,
            shortDescription: "Kanban SDD+TDD, Cronograma Gantt (UFAL 2026.2), Rede PERT/CPM e Matriz RACI do SmartSales RAG"
          }) {
            projectV2 { id }
          }
        }
        """,
        {"projectId": project_id, "repoId": repo_id},
    )

    # Fetch existing fields
    fields_data = graphql(
        """
        query($projectId: ID!) {
          node(id: $projectId) {
            ... on ProjectV2 {
              fields(first: 50) {
                nodes {
                  ... on ProjectV2Field { id name dataType }
                  ... on ProjectV2SingleSelectField { id name options { id name } }
                }
              }
            }
          }
        }
        """,
        {"projectId": project_id},
    )
    fields = {f["name"]: f for f in fields_data["node"]["fields"]["nodes"] if "name" in f}

    def ensure_single_select(name, options):
        if name in fields:
            return fields[name]
        res = graphql(
            """
            mutation($projectId: ID!, $name: String!, $options: [ProjectV2SingleSelectFieldOptionInput!]!) {
              createProjectV2Field(input: {
                projectId: $projectId,
                dataType: SINGLE_SELECT,
                name: $name,
                singleSelectOptions: $options
              }) {
                projectV2Field {
                  ... on ProjectV2SingleSelectField { id name options { id name } }
                }
              }
            }
            """,
            {"projectId": project_id, "name": name, "options": options},
        )
        fields[name] = res["createProjectV2Field"]["projectV2Field"]
        return fields[name]

    def ensure_field(name, data_type):
        if name in fields:
            return fields[name]
        res = graphql(
            """
            mutation($projectId: ID!, $name: String!, $dataType: ProjectV2CustomFieldType!) {
              createProjectV2Field(input: {
                projectId: $projectId,
                dataType: $dataType,
                name: $name
              }) {
                projectV2Field {
                  ... on ProjectV2Field { id name dataType }
                }
              }
            }
            """,
            {"projectId": project_id, "name": name, "dataType": data_type},
        )
        fields[name] = res["createProjectV2Field"]["projectV2Field"]
        return fields[name]

    sprint_field = ensure_single_select(
        "Sprint",
        [
            {"name": "Sprint 1 (22/09–02/10)", "color": "GREEN", "description": "Marco M1 — Fundação e Contratos"},
            {"name": "Sprint 2 (05/10–16/10)", "color": "BLUE", "description": "Marco M2 — Streaming SSE Ponta a Ponta"},
            {"name": "Sprint 3 (19/10–30/10)", "color": "PURPLE", "description": "Marco M3 — RAG Fiel, Guardrails e Cache"},
            {"name": "Sprint 4 (03/11–13/11)", "color": "YELLOW", "description": "Marco M4 — Vendas Consultivas e Checkout"},
            {"name": "Homologação & M5 (16/11–24/11)", "color": "RED", "description": "Marco M5 — E2E, Demo e Entrega Final UFAL"},
        ],
    )
    layer_field = ensure_single_select(
        "Camada",
        [
            {"name": "Gerência & PM", "color": "BLUE", "description": "G01–G04 e Monitoramento Contínuo"},
            {"name": "Backend & IA (RAG)", "color": "PURPLE", "description": "B01–B05 (PostgreSQL pgvector, LangChain, Guardrails)"},
            {"name": "Middle-end & Gateway", "color": "GREEN", "description": "M01–M05 (FastAPI, SSE, Redis, Checkout Mock)"},
            {"name": "Frontend & UX", "color": "ORANGE", "description": "F01–F04 (Next.js, Chat SSE, Product Cards)"},
            {"name": "QA & Homologação", "color": "RED", "description": "B05 e F05 (RAGAS Golden Set e Playwright E2E)"},
        ],
    )
    cpm_field = ensure_single_select(
        "Caminho Crítico (CPM)",
        [
            {"name": "CRÍTICO (Folga 0d)", "color": "RED", "description": "Caminho Crítico Determinístico (Folga = 0 dias úteis)"},
            {"name": "Quase Crítico (Folga 1d)", "color": "ORANGE", "description": "Trilha Quase Crítica (Folga = 1 dia útil)"},
            {"name": "Folga Normal (> 1d)", "color": "GREEN", "description": "Atividade com folga operacional (> 1 dia útil)"},
        ],
    )
    start_field = ensure_field("Data de Início", "DATE")
    end_field = ensure_field("Data de Término (Prazo)", "DATE")
    dur_field = ensure_field("Duração (Dias Úteis)", "NUMBER")
    float_field = ensure_field("Folga CPM", "TEXT")
    raci_a_field = ensure_field("Aprovador RACI (A)", "TEXT")
    raci_r_field = ensure_field("Responsáveis RACI (R)", "TEXT")

    status_field = fields["Status"]
    status_options = {o["name"]: o["id"] for o in status_field["options"]}
    sprint_options = {o["name"]: o["id"] for o in sprint_field["options"]}
    layer_options = {o["name"]: o["id"] for o in layer_field["options"]}
    cpm_options = {o["name"]: o["id"] for o in cpm_field["options"]}

    for issue in issues:
        prefix = next((k for k in ITEMS_METADATA if issue["title"].startswith(k)), None)
        if not prefix:
            continue
        meta = ITEMS_METADATA[prefix]

        add_res = graphql(
            """
            mutation($projectId: ID!, $contentId: ID!) {
              addProjectV2ItemById(input: {projectId: $projectId, contentId: $contentId}) {
                item { id }
              }
            }
            """,
            {"projectId": project_id, "contentId": issue["id"]},
        )
        item_id = add_res["addProjectV2ItemById"]["item"]["id"]

        def set_val(field_id, value_dict):
            graphql(
                """
                mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $value: ProjectV2FieldValue!) {
                  updateProjectV2ItemFieldValue(input: {
                    projectId: $projectId,
                    itemId: $itemId,
                    fieldId: $fieldId,
                    value: $value
                  }) {
                    projectV2Item { id }
                  }
                }
                """,
                {"projectId": project_id, "itemId": item_id, "fieldId": field_id, "value": value_dict},
            )

        # Match status option (Todo / In Progress / Done)
        target_status = meta["status"]
        status_opt_id = status_options.get(target_status)
        if not status_opt_id:
            for k, v in status_options.items():
                if target_status.lower() in k.lower():
                    status_opt_id = v
                    break
        if status_opt_id:
            set_val(status_field["id"], {"singleSelectOptionId": status_opt_id})

        set_val(sprint_field["id"], {"singleSelectOptionId": sprint_options[meta["sprint"]]})
        set_val(layer_field["id"], {"singleSelectOptionId": layer_options[meta["layer"]]})
        set_val(cpm_field["id"], {"singleSelectOptionId": cpm_options[meta["cpm"]]})
        set_val(start_field["id"], {"date": meta["start"]})
        set_val(end_field["id"], {"date": meta["end"]})
        set_val(dur_field["id"], {"number": float(meta["duration"])})
        set_val(float_field["id"], {"text": meta["float"]})
        set_val(raci_a_field["id"], {"text": meta["raci_a"]})
        set_val(raci_r_field["id"], {"text": meta["raci_r"]})
        print(f"Configured Project item for Issue #{issue['number']}: {prefix}")

    print(f"\nProject V2 fully populated: {project['url']}")


if __name__ == "__main__":
    main()
