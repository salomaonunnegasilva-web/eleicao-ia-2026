import datetime
import hashlib
from sqlalchemy.orm import Session
from app.db.models import Party, Candidate, Poll, PollResult, Document, DocumentChunk
from app.rag.ingest import chunk_text, get_embedding

def seed_all(db: Session):
    # 1. Seed Parties
    parties_data = [
        {"name": "Partido dos Trabalhadores", "abbreviation": "PT", "number": 13},
        {"name": "Partido Liberal", "abbreviation": "PL", "number": 22},
        {"name": "Movimento Democrático Brasileiro", "abbreviation": "MDB", "number": 15},
        {"name": "Partido Novo", "abbreviation": "Novo", "number": 30},
        {"name": "Partido Democrático Trabalhista", "abbreviation": "PDT", "number": 12},
        {"name": "Partido da Social Democracia Brasileira", "abbreviation": "PSDB", "number": 45},
        {"name": "Republicanos", "abbreviation": "Republicanos", "number": 10},
    ]

    parties = {}
    for p_info in parties_data:
        existing = db.query(Party).filter(Party.abbreviation == p_info["abbreviation"]).first()
        if not existing:
            party = Party(**p_info)
            db.add(party)
            db.flush()
            parties[p_info["abbreviation"]] = party
        else:
            parties[p_info["abbreviation"]] = existing

    # 2. Seed Candidates (speculative/historical for 2026 election)
    candidates_data = [
        {"name": "Luiz Inácio Lula da Silva", "abbreviation": "PT", "coalition": "Cenário demonstrativo", "status": "Hipotético (demo)", "expenses": None, "attendance": None, "bills": None},
        {"name": "Tarcísio de Freitas", "abbreviation": "Republicanos", "coalition": "Cenário demonstrativo", "status": "Hipotético (demo)", "expenses": None, "attendance": None, "bills": None},
        {"name": "Ciro Gomes", "abbreviation": "PDT", "coalition": "Cenário demonstrativo", "status": "Hipotético (demo)", "expenses": None, "attendance": None, "bills": None},
        {"name": "Romeu Zema", "abbreviation": "Novo", "coalition": "Cenário demonstrativo", "status": "Hipotético (demo)", "expenses": None, "attendance": None, "bills": None},
        {"name": "Simone Tebet", "abbreviation": "MDB", "coalition": "Cenário demonstrativo", "status": "Hipotético (demo)", "expenses": None, "attendance": None, "bills": None},
        {"name": "Branco/Nulo", "abbreviation": None, "coalition": None, "status": "Categoria de resposta", "expenses": None, "attendance": None, "bills": None},
        {"name": "Não Sabe/Indeciso", "abbreviation": None, "coalition": None, "status": "Categoria de resposta", "expenses": None, "attendance": None, "bills": None},
    ]

    candidates = {}
    for c_info in candidates_data:
        existing = db.query(Candidate).filter(Candidate.name == c_info["name"]).first()
        p_id = parties[c_info["abbreviation"]].id if c_info["abbreviation"] else None
        if not existing:
            candidate = Candidate(
                name=c_info["name"],
                party_id=p_id,
                coalition=c_info["coalition"],
                status=c_info["status"],
                election_year=2026,
                congress_expenses=c_info["expenses"],
                session_attendance=c_info["attendance"],
                bills_proposed=c_info["bills"]
            )
            db.add(candidate)
            db.flush()
            candidates[c_info["name"]] = candidate
        else:
            existing.party_id = p_id
            existing.coalition = c_info["coalition"]
            existing.status = c_info["status"]
            existing.congress_expenses = c_info["expenses"]
            existing.session_attendance = c_info["attendance"]
            existing.bills_proposed = c_info["bills"]
            candidates[c_info["name"]] = existing

    db.commit()

    # 3. Seed Polls and Poll Results
    # We create 5 polls distributed from March to June 2026
    polls_data = [
        {
            "pollster": "Instituto Demo A",
            "registration_id": "DEMO-001/2026",
            "legacy_registration_id": "BR-00101/2026",
            "fieldwork_start": datetime.date(2026, 3, 11),
            "fieldwork_end": datetime.date(2026, 3, 13),
            "publication_date": datetime.date(2026, 3, 14),
            "sample_size": 2500,
            "geography": "Nacional",
            "methodology": "Dados sintéticos: entrevistas presenciais simuladas",
            "source_url": None,
            "results": [
                # Round 1
                {"candidate": "Luiz Inácio Lula da Silva", "vote_intention": 38.0, "scenario": "Estimulada Turno 1", "round": 1, "moe": 2.0},
                {"candidate": "Tarcísio de Freitas", "vote_intention": 28.0, "scenario": "Estimulada Turno 1", "round": 1, "moe": 2.0},
                {"candidate": "Ciro Gomes", "vote_intention": 8.0, "scenario": "Estimulada Turno 1", "round": 1, "moe": 2.0},
                {"candidate": "Romeu Zema", "vote_intention": 6.0, "scenario": "Estimulada Turno 1", "round": 1, "moe": 2.0},
                {"candidate": "Simone Tebet", "vote_intention": 5.0, "scenario": "Estimulada Turno 1", "round": 1, "moe": 2.0},
                {"candidate": "Branco/Nulo", "vote_intention": 9.0, "scenario": "Estimulada Turno 1", "round": 1, "moe": 2.0},
                {"candidate": "Não Sabe/Indeciso", "vote_intention": 6.0, "scenario": "Estimulada Turno 1", "round": 1, "moe": 2.0},
                # Round 2
                {"candidate": "Luiz Inácio Lula da Silva", "vote_intention": 45.0, "scenario": "Turno 2: Lula vs Tarcísio", "round": 2, "moe": 2.0},
                {"candidate": "Tarcísio de Freitas", "vote_intention": 38.0, "scenario": "Turno 2: Lula vs Tarcísio", "round": 2, "moe": 2.0},
                {"candidate": "Branco/Nulo", "vote_intention": 12.0, "scenario": "Turno 2: Lula vs Tarcísio", "round": 2, "moe": 2.0},
                {"candidate": "Não Sabe/Indeciso", "vote_intention": 5.0, "scenario": "Turno 2: Lula vs Tarcísio", "round": 2, "moe": 2.0},
            ]
        },
        {
            "pollster": "Instituto Demo B",
            "registration_id": "DEMO-002/2026",
            "legacy_registration_id": "BR-00203/2026",
            "fieldwork_start": datetime.date(2026, 4, 4),
            "fieldwork_end": datetime.date(2026, 4, 6),
            "publication_date": datetime.date(2026, 4, 7),
            "sample_size": 2000,
            "geography": "Nacional",
            "methodology": "Dados sintéticos: entrevistas em pontos de fluxo simuladas",
            "source_url": None,
            "results": [
                # Round 1
                {"candidate": "Luiz Inácio Lula da Silva", "vote_intention": 37.0, "scenario": "Estimulada Turno 1", "round": 1, "moe": 2.2},
                {"candidate": "Tarcísio de Freitas", "vote_intention": 29.0, "scenario": "Estimulada Turno 1", "round": 1, "moe": 2.2},
                {"candidate": "Ciro Gomes", "vote_intention": 7.0, "scenario": "Estimulada Turno 1", "round": 1, "moe": 2.2},
                {"candidate": "Romeu Zema", "vote_intention": 7.0, "scenario": "Estimulada Turno 1", "round": 1, "moe": 2.2},
                {"candidate": "Simone Tebet", "vote_intention": 4.0, "scenario": "Estimulada Turno 1", "round": 1, "moe": 2.2},
                {"candidate": "Branco/Nulo", "vote_intention": 10.0, "scenario": "Estimulada Turno 1", "round": 1, "moe": 2.2},
                {"candidate": "Não Sabe/Indeciso", "vote_intention": 6.0, "scenario": "Estimulada Turno 1", "round": 1, "moe": 2.2},
                # Round 2
                {"candidate": "Luiz Inácio Lula da Silva", "vote_intention": 44.0, "scenario": "Turno 2: Lula vs Tarcísio", "round": 2, "moe": 2.2},
                {"candidate": "Tarcísio de Freitas", "vote_intention": 39.0, "scenario": "Turno 2: Lula vs Tarcísio", "round": 2, "moe": 2.2},
                {"candidate": "Branco/Nulo", "vote_intention": 12.0, "scenario": "Turno 2: Lula vs Tarcísio", "round": 2, "moe": 2.2},
                {"candidate": "Não Sabe/Indeciso", "vote_intention": 5.0, "scenario": "Turno 2: Lula vs Tarcísio", "round": 2, "moe": 2.2},
            ]
        },
        {
            "pollster": "Instituto Demo C",
            "registration_id": "DEMO-003/2026",
            "legacy_registration_id": "BR-00305/2026",
            "fieldwork_start": datetime.date(2026, 5, 12),
            "fieldwork_end": datetime.date(2026, 5, 16),
            "publication_date": datetime.date(2026, 5, 18),
            "sample_size": 3000,
            "geography": "Nacional",
            "methodology": "Dados sintéticos: painel web simulado",
            "source_url": None,
            "results": [
                # Round 1
                {"candidate": "Luiz Inácio Lula da Silva", "vote_intention": 39.5, "scenario": "Estimulada Turno 1", "round": 1, "moe": 1.8},
                {"candidate": "Tarcísio de Freitas", "vote_intention": 31.0, "scenario": "Estimulada Turno 1", "round": 1, "moe": 1.8},
                {"candidate": "Ciro Gomes", "vote_intention": 6.5, "scenario": "Estimulada Turno 1", "round": 1, "moe": 1.8},
                {"candidate": "Romeu Zema", "vote_intention": 5.5, "scenario": "Estimulada Turno 1", "round": 1, "moe": 1.8},
                {"candidate": "Simone Tebet", "vote_intention": 5.0, "scenario": "Estimulada Turno 1", "round": 1, "moe": 1.8},
                {"candidate": "Branco/Nulo", "vote_intention": 7.5, "scenario": "Estimulada Turno 1", "round": 1, "moe": 1.8},
                {"candidate": "Não Sabe/Indeciso", "vote_intention": 5.0, "scenario": "Estimulada Turno 1", "round": 1, "moe": 1.8},
                # Round 2
                {"candidate": "Luiz Inácio Lula da Silva", "vote_intention": 47.0, "scenario": "Turno 2: Lula vs Tarcísio", "round": 2, "moe": 1.8},
                {"candidate": "Tarcísio de Freitas", "vote_intention": 42.0, "scenario": "Turno 2: Lula vs Tarcísio", "round": 2, "moe": 1.8},
                {"candidate": "Branco/Nulo", "vote_intention": 7.0, "scenario": "Turno 2: Lula vs Tarcísio", "round": 2, "moe": 1.8},
                {"candidate": "Não Sabe/Indeciso", "vote_intention": 4.0, "scenario": "Turno 2: Lula vs Tarcísio", "round": 2, "moe": 1.8},
            ]
        },
        {
            "pollster": "Instituto Demo A",
            "registration_id": "DEMO-004/2026",
            "legacy_registration_id": "BR-00408/2026",
            "fieldwork_start": datetime.date(2026, 6, 2),
            "fieldwork_end": datetime.date(2026, 6, 4),
            "publication_date": datetime.date(2026, 6, 5),
            "sample_size": 2500,
            "geography": "Nacional",
            "methodology": "Dados sintéticos: entrevistas presenciais simuladas",
            "source_url": None,
            "results": [
                # Round 1
                {"candidate": "Luiz Inácio Lula da Silva", "vote_intention": 37.5, "scenario": "Estimulada Turno 1", "round": 1, "moe": 2.0},
                {"candidate": "Tarcísio de Freitas", "vote_intention": 31.5, "scenario": "Estimulada Turno 1", "round": 1, "moe": 2.0},
                {"candidate": "Ciro Gomes", "vote_intention": 6.0, "scenario": "Estimulada Turno 1", "round": 1, "moe": 2.0},
                {"candidate": "Romeu Zema", "vote_intention": 5.0, "scenario": "Estimulada Turno 1", "round": 1, "moe": 2.0},
                {"candidate": "Simone Tebet", "vote_intention": 4.5, "scenario": "Estimulada Turno 1", "round": 1, "moe": 2.0},
                {"candidate": "Branco/Nulo", "vote_intention": 9.5, "scenario": "Estimulada Turno 1", "round": 1, "moe": 2.0},
                {"candidate": "Não Sabe/Indeciso", "vote_intention": 6.0, "scenario": "Estimulada Turno 1", "round": 1, "moe": 2.0},
                # Round 2
                {"candidate": "Luiz Inácio Lula da Silva", "vote_intention": 46.0, "scenario": "Turno 2: Lula vs Tarcísio", "round": 2, "moe": 2.0},
                {"candidate": "Tarcísio de Freitas", "vote_intention": 42.0, "scenario": "Turno 2: Lula vs Tarcísio", "round": 2, "moe": 2.0},
                {"candidate": "Branco/Nulo", "vote_intention": 8.0, "scenario": "Turno 2: Lula vs Tarcísio", "round": 2, "moe": 2.0},
                {"candidate": "Não Sabe/Indeciso", "vote_intention": 4.0, "scenario": "Turno 2: Lula vs Tarcísio", "round": 2, "moe": 2.0},
            ]
        },
        {
            "pollster": "Instituto Demo B",
            "registration_id": "DEMO-005/2026",
            "legacy_registration_id": "BR-00512/2026",
            "fieldwork_start": datetime.date(2026, 6, 9),
            "fieldwork_end": datetime.date(2026, 6, 11),
            "publication_date": datetime.date(2026, 6, 12),
            "sample_size": 2000,
            "geography": "Nacional",
            "methodology": "Dados sintéticos: entrevistas em pontos de fluxo simuladas",
            "source_url": None,
            "results": [
                # Round 1
                {"candidate": "Luiz Inácio Lula da Silva", "vote_intention": 38.2, "scenario": "Estimulada Turno 1", "round": 1, "moe": 2.2},
                {"candidate": "Tarcísio de Freitas", "vote_intention": 32.1, "scenario": "Estimulada Turno 1", "round": 1, "moe": 2.2},
                {"candidate": "Ciro Gomes", "vote_intention": 5.8, "scenario": "Estimulada Turno 1", "round": 1, "moe": 2.2},
                {"candidate": "Romeu Zema", "vote_intention": 5.2, "scenario": "Estimulada Turno 1", "round": 1, "moe": 2.2},
                {"candidate": "Simone Tebet", "vote_intention": 4.3, "scenario": "Estimulada Turno 1", "round": 1, "moe": 2.2},
                {"candidate": "Branco/Nulo", "vote_intention": 9.0, "scenario": "Estimulada Turno 1", "round": 1, "moe": 2.2},
                {"candidate": "Não Sabe/Indeciso", "vote_intention": 5.4, "scenario": "Estimulada Turno 1", "round": 1, "moe": 2.2},
                # Round 2
                {"candidate": "Luiz Inácio Lula da Silva", "vote_intention": 45.8, "scenario": "Turno 2: Lula vs Tarcísio", "round": 2, "moe": 2.2},
                {"candidate": "Tarcísio de Freitas", "vote_intention": 43.1, "scenario": "Turno 2: Lula vs Tarcísio", "round": 2, "moe": 2.2},
                {"candidate": "Branco/Nulo", "vote_intention": 7.5, "scenario": "Turno 2: Lula vs Tarcísio", "round": 2, "moe": 2.2},
                {"candidate": "Não Sabe/Indeciso", "vote_intention": 3.6, "scenario": "Turno 2: Lula vs Tarcísio", "round": 2, "moe": 2.2},
            ]
        }
    ]

    for p_info in polls_data:
        existing_poll = db.query(Poll).filter(
            Poll.registration_id.in_(
                [p_info["registration_id"], p_info["legacy_registration_id"]]
            )
        ).first()
        if not existing_poll:
            poll = Poll(
                pollster=p_info["pollster"],
                registration_id=p_info["registration_id"],
                fieldwork_start=p_info["fieldwork_start"],
                fieldwork_end=p_info["fieldwork_end"],
                publication_date=p_info["publication_date"],
                sample_size=p_info["sample_size"],
                geography=p_info["geography"],
                methodology=p_info["methodology"],
                source_url=p_info["source_url"]
            )
            db.add(poll)
            db.flush()

            for r in p_info["results"]:
                res = PollResult(
                    poll_id=poll.id,
                    candidate_id=candidates[r["candidate"]].id,
                    vote_intention=r["vote_intention"],
                    scenario_name=r["scenario"],
                    round=r["round"],
                    margin_of_error=r["moe"]
                )
                db.add(res)
        else:
            existing_poll.pollster = p_info["pollster"]
            existing_poll.registration_id = p_info["registration_id"]
            existing_poll.fieldwork_start = p_info["fieldwork_start"]
            existing_poll.fieldwork_end = p_info["fieldwork_end"]
            existing_poll.publication_date = p_info["publication_date"]
            existing_poll.sample_size = p_info["sample_size"]
            existing_poll.geography = p_info["geography"]
            existing_poll.methodology = p_info["methodology"]
            existing_poll.source_url = p_info["source_url"]
    db.commit()

    # 4. Seed Documents (RAG base)
    docs_data = [
        {
            "title": "[DEMO] Calendário eleitoral 2026 - resumo demonstrativo",
            "legacy_title": "Calendário Eleitoral Oficial das Eleições 2026 - TSE",
            "source_type": "demo_calendar",
            "source_url": "https://www.tse.jus.br/eleicoes/calendario-eleitoral/calendario-eleitoral",
            "author": "Dataset sintético para portfólio",
            "publication_date": datetime.date(2026, 1, 15),
            "candidate_name": None,
            "party_abbr": None,
            "text": """
            AVISO: CONTEÚDO DEMONSTRATIVO. CONFIRME DATAS E PRAZOS NO TSE.
            RESUMO DO CALENDÁRIO ELEITORAL 2026

            As eleições ordinárias de 2026 no Brasil realizar-se-ão em todo o país nos seguintes dias:
            - Primeiro turno: 4 de outubro de 2026 (primeiro domingo de outubro)
            - Segundo turno (onde houver): 25 de outubro de 2026 (último domingo de outubro)

            Principais prazos da Justiça Eleitoral e do PesqEle para o ano eleitoral de 2026:
            1. Registro de pesquisas eleitorais: Desde 1º de janeiro de 2026, todas as entidades e empresas que realizarem pesquisas de opinião pública relativas às eleições de 2026, para conhecimento público, são obrigadas a registrar cada pesquisa no Sistema de Registro de Pesquisas Eleitorais (PesqEle) do TSE até 5 (cinco) dias antes da divulgação.
            2. Filiação partidária e domicílio eleitoral: O prazo final para que candidatos estejam filiados a partidos políticos e com domicílio eleitoral fixado na circunscrição em que pretendem concorrer é 4 de abril de 2026 (6 meses antes do pleito).
            3. Convenções partidárias: As convenções destinadas a deliberar sobre coligações e escolher candidatos e candidatas a presidente, vice-presidente, governador, senador e deputados federais/estaduais devem ocorrer de 20 de julho a 5 de agosto de 2026.
            4. Registro de candidaturas: Os partidos políticos e coligações devem solicitar o registro de seus candidatos até às 19h do dia 15 de agosto de 2026.
            5. Propaganda eleitoral geral: A propaganda eleitoral, inclusive na internet, é permitida a partir de 16 de agosto de 2026. O horário eleitoral gratuito no rádio e na televisão começará em 28 de agosto de 2026 e terminará em 1º de outubro de 2026.
            """
        },
        {
            "title": "[DEMO] Cenário sintético de propostas - Lula (economia)",
            "legacy_title": "Linhas Gerais de Governo - Luiz Inácio Lula da Silva (Reforma Tributária e Economia)",
            "source_type": "demo_policy_scenario",
            "source_url": None,
            "author": "Dataset sintético para portfólio",
            "publication_date": datetime.date(2026, 5, 20),
            "candidate_name": "Luiz Inácio Lula da Silva",
            "party_abbr": "PT",
            "text": """
            AVISO: CENÁRIO HIPOTÉTICO PARA DEMONSTRAÇÃO TÉCNICA. NÃO É PROGRAMA OFICIAL.
            DIRETRIZES ECONÔMICAS E REFORMA TRIBUTÁRIA - CENÁRIO SINTÉTICO

            A consolidação da Reforma Tributária sobre o consumo é a prioridade central da gestão econômica para o próximo período. O candidato defende a implantação célere do Imposto sobre Bens e Serviços (IBS) e da Contribuição sobre Bens e Serviços (CBS) para simplificar a tributação e incentivar a produtividade.

            Pilares da proposta econômica:
            1. Justiça Tributária e Progressividade: Propõe a isenção do Imposto de Renda (IRPF) para trabalhadores que ganham até R$ 5.000, compensando a perda de arrecadação por meio da tributação de grandes fortunas, lucros e dividendos distribuídos, e aumento de alíquotas para rendimentos financeiros de super-ricos.
            2. Cashback do Povo: Fortalecimento do mecanismo de devolução imediata de tributos sobre produtos da cesta básica e serviços essenciais (água, luz, esgoto) para famílias de baixa renda inscritas no Cadastro Único (CadÚnico).
            3. Reindustrialização Verde: Apoio a investimentos em energias renováveis e descarbonização das indústrias nacionais, utilizando fundos públicos (BNDES e Fundo Clima) como indutores da transição energética.
            4. Controle da Inflação e Juros: Foco no aumento real do salário mínimo anual acima da inflação e manutenção da autonomia do Banco Central, buscando contudo uma coordenação mais estreita entre políticas fiscais progressivas e o comitê de política monetária (Copom) para redução estrutural das taxas de juros.
            """
        },
        {
            "title": "[DEMO] Cenário sintético de propostas - Tarcísio (gestão)",
            "legacy_title": "Plano de Governo para o Brasil - Tarcísio de Freitas (Infraestrutura, Impostos e Gestão)",
            "source_type": "demo_policy_scenario",
            "source_url": None,
            "author": "Dataset sintético para portfólio",
            "publication_date": datetime.date(2026, 5, 25),
            "candidate_name": "Tarcísio de Freitas",
            "party_abbr": "Republicanos",
            "text": """
            AVISO: CENÁRIO HIPOTÉTICO PARA DEMONSTRAÇÃO TÉCNICA. NÃO É PROGRAMA OFICIAL.
            DIRETRIZES DE ESTADO E REFORMA TRIBUTÁRIA - CENÁRIO SINTÉTICO

            O modelo de desenvolvimento econômico defendido pelo candidato pauta-se pela atração de capital privado, concessões de infraestrutura, responsabilidade fiscal rígida e desoneração tributária para produtores e empreendedores.

            Pilares da proposta econômica:
            1. Desoneração e Simplificação: O candidato defende que a reforma tributária deve focar prioritariamente na redução da carga sobre o setor produtivo (indústria, comércio e agronegócio), reduzindo impostos sobre a folha de pagamento e unificando alíquotas do IBS/CBS na menor faixa possível para evitar o aumento da carga tributária total do país.
            2. Privatizações e Concessões: Propõe um amplo programa de parcerias público-privadas (PPPs) em infraestrutura (portos, aeroportos, ferrovias e rodovias), saneamento básico e presídios, seguindo o modelo adotado no Estado de São Paulo.
            3. Eficiência Administrativa: Propõe uma ampla reforma administrativa no nível federal, com redução do número de ministérios, corte de cargos comissionados, digitalização de serviços públicos e avaliação contínua de desempenho do funcionalismo.
            4. Âncora Fiscal Rígida: Defesa irredutível do cumprimento do arcabouço fiscal, com estabelecimento de limites mais estritos para despesas públicas não-obrigatórias e oposição a qualquer nova forma de imposto federal sobre transações, riqueza ou propriedade.
            """
        },
        {
            "title": "[DEMO] Cenário sintético de propostas - Ciro (desenvolvimento)",
            "legacy_title": "Projeto Nacional de Desenvolvimento (PND) - Ciro Gomes (Educação, Indústria e Dívida)",
            "source_type": "demo_policy_scenario",
            "source_url": None,
            "author": "Dataset sintético para portfólio",
            "publication_date": datetime.date(2026, 4, 18),
            "candidate_name": "Ciro Gomes",
            "party_abbr": "PDT",
            "text": """
            AVISO: CENÁRIO HIPOTÉTICO PARA DEMONSTRAÇÃO TÉCNICA. NÃO É PROGRAMA OFICIAL.
            PROJETO NACIONAL DE DESENVOLVIMENTO - CENÁRIO SINTÉTICO

            O PND propõe uma ruptura estrutural com o modelo econômico atual do país, defendendo um papel ativo e planejador do Estado no desenvolvimento industrial e científico.

            Pilares da proposta econômica e social:
            1. Educação em Tempo Integral: Expansão do modelo de escolas de tempo integral para todo o território nacional, focado na capacitação técnica e científica de jovens. Propõe que 10% do PIB seja destinado à educação pública.
            2. Renegociação de Dívidas: Criação de um programa nacional de refinanciamento de dívidas para famílias inscritas no SCPC e Serasa, subsidiado em parte por garantias públicas de longo prazo.
            3. Retomada da Indústria: Implementação de impostos seletivos de importação para proteger indústrias nacionais de base tecnológica e subsídios diretos para a fabricação de semicondutores, químicos finos e fármacos em solo nacional.
            4. Reforma Tributária Progressiva: Unificação de impostos federais e criação do Imposto sobre Grandes Fortunas (IGF) a partir de patrimônios superiores a R$ 20 milhões, além de imposto progressivo sobre heranças e doações.
            """
        },
        {
            "title": "[DEMO] Cenário sintético de propostas - Zema (gestão)",
            "legacy_title": "Carta ao Brasil e Liberdade Econômica - Romeu Zema (Descentralização e Gestão Eficiente)",
            "source_type": "demo_policy_scenario",
            "source_url": None,
            "author": "Dataset sintético para portfólio",
            "publication_date": datetime.date(2026, 5, 2),
            "candidate_name": "Romeu Zema",
            "party_abbr": "Novo",
            "text": """
            AVISO: CENÁRIO HIPOTÉTICO PARA DEMONSTRAÇÃO TÉCNICA. NÃO É PROGRAMA OFICIAL.
            DIRETRIZES DE LIBERDADE ECONÔMICA E GESTÃO - CENÁRIO SINTÉTICO

            A proposta do candidato fundamenta-se na descentralização administrativa, na facilitação de novos negócios por meio do fim da burocracia e no equilíbrio fiscal como pré-requisito para o crescimento social estável.

            Pilares da proposta econômica:
            1. Fim da Burocracia: Implementação federal da Lei de Liberdade Econômica de forma irrestrita, com dispensa automática de alvarás de funcionamento para atividades de baixo risco e facilitação do registro de MEIs e pequenas empresas.
            2. Equilíbrio das Contas Públicas: Propõe reformas fiscais duras para controlar o crescimento dos gastos correntes com servidores e inativos, além do congelamento de contratações públicas federais temporárias e revisão de todos os benefícios fiscais corporativos.
            3. Pacto Federativo: Revisão da distribuição de recursos tributários federais para garantir que a maior fatia dos impostos permaneça diretamente nos municípios e estados brasileiros, sob o lema "Mais Brasil, Menos Brasília".
            4. Privatização de Estatais: Privatização completa de grandes corporações estatais como Petrobras, Correios e bancos públicos federais (com exceção do papel de fomento do Banco do Brasil e Caixa Econômica Federal a curto prazo).
            """
        }
    ]

    for d_info in docs_data:
        c_id = candidates[d_info["candidate_name"]].id if d_info["candidate_name"] else None
        p_id = parties[d_info["party_abbr"]].id if d_info["party_abbr"] else None

        existing_doc = db.query(Document).filter(
            Document.title.in_([d_info["title"], d_info["legacy_title"]])
        ).first()
        if existing_doc is None:
            existing_doc = Document()
            db.add(existing_doc)

        existing_doc.title = d_info["title"]
        existing_doc.raw_text = d_info["text"]
        existing_doc.source_type = d_info["source_type"]
        existing_doc.source_url = d_info["source_url"]
        existing_doc.author = d_info["author"]
        existing_doc.publication_date = d_info["publication_date"]
        existing_doc.candidate_id = c_id
        existing_doc.party_id = p_id
        existing_doc.jurisdiction = "Federal"
        existing_doc.checksum = hashlib.sha256(d_info["text"].encode("utf-8")).hexdigest()
        db.flush()

        existing_doc.chunks.clear()
        db.flush()
        for idx, text_value in enumerate(chunk_text(d_info["text"])):
            db.add(
                DocumentChunk(
                    document_id=existing_doc.id,
                    chunk_text=text_value,
                    chunk_index=idx,
                    embedding=get_embedding(text_value),
                    metadata_json={
                        "title": d_info["title"],
                        "source_type": d_info["source_type"],
                        "publication_date": str(d_info["publication_date"]),
                        "chunk_index": idx,
                        "synthetic": True,
                    },
                )
            )

    db.commit()
