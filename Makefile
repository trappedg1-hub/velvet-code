.PHONY: help test canon-check canon-render sync probe next tasks list-draft sprites reindex qa qa-render prompts forge tags arena-task atlas corpus miner tournament clean

help:
	@echo "make test          — pytest"
	@echo "make canon-check   — гейт утверждений (CI-блокер)"
	@echo "make sync          — canon/source/*.json -> реестр"
	@echo "make canon-render  — пересобрать лист на утверждение"
	@echo "make list-draft    — что ждёт утверждения"
	@echo "make probe         — диагностика мозга (AC_PROVIDER=arena-bridge|mock)"
	@echo "make next          — следующая доступная задача для агента"
	@echo "make tasks         — очередь задач целиком"
	@echo "make sprites       — хромакей сырых рендеров в игровые спрайты"
	@echo "make qa            — проверка спрайтов (кадр, альфа, формат) — блокер приёмки"
	@echo "make qa-render     — приёмка рендеров по артефактам (бахрома, обрез, мыло, перекос)"
	@echo "make prompts       — пример раскрытия wildcard-шаблона промпта"
	@echo "make forge-heroine — промпт героини под модель и уровень горячести (HEROINE=selena HEAT=2 MODEL=illustrious)"
	@echo "make tags          — база тегов Danbooru с частотами (QUERY=thigh)"
	@echo "make arena-task    — самодостаточная задача агенту (HEROINE=reika KIND=render)"
	@echo "make atlas         — атлас явной лексики с частотами Danbooru"
	@echo "make corpus        — добрать корпус промптов (PAGES=20)"
	@echo "make miner         — частоты корпуса: блоки качества, негативы, LoRA"
	@echo "make tournament    — пакет турнира для агентов (HEROINE=selena)"

test:
	python3 -m pytest tests -q

canon-check:
	python3 -m automation.canon check

sync:
	python3 -m automation.canon sync

canon-render: sync
	python3 -m automation.canon render

list-draft:
	python3 -m automation.canon list --status draft

probe:
	python3 -m automation.agent_client --provider $${AC_PROVIDER:-mock}

next:
	python3 -m automation.tasks next

tasks:
	python3 -m automation.tasks list

sprites:
	python3 tools/pipeline_sprites.py $${NAMES}

reindex:
	python3 tools/pipeline_sprites.py --reindex

qa:
	python3 tools/qa_sprites.py

qa-render:
	python3 tools/qa_render.py

prompts:
	python3 tools/prompt_build.py --template "masterpiece, best quality, manhwa style, {2$$__body_curvy__}, __outfit_l2plus__, __pose_ecchi__, __camera__, (huge breasts:1.3)" -n 3 --seed 7

forge-heroine:
	python3 tools/prompt_forge.py --heroine $${HEROINE:-selena} --model $${MODEL:-illustrious} --heat $${HEAT:-2} --ladder

tags:
	python3 tools/tag_db.py --search "$${QUERY:-thigh}" --limit 20

arena-task:
	python3 tools/arena_task.py --heroine $${HEROINE:-reika} --kind $${KIND:-render} --heat $${HEAT:-2}

atlas:
	python3 tools/tag_db.py --atlas

corpus:
	python3 tools/corpus_fetch.py --source jtatman --pages $${PAGES:-20}

miner:
	python3 tools/prompt_miner.py --top 20

tournament:
	python3 tools/arena_task.py --heroine $${HEROINE:-selena} --kind tournament --heat $${HEAT:-2} --model $${MODEL:-illustrious}

foot:
	python3 tools/foot_spec.py --block

foot-views:
	python3 tools/foot_spec.py --views

foot-check:
	python3 tools/foot_spec.py --check "$${P:-barefoot, foot in three-quarter view}" "$${N:-long feet, flat feet, splayed toes}"

render:
	python3 -m automation.arena_loop plan --agents $${AGENTS:-16}

boldness:
	python3 tools/boldness.py --heroine $${HEROINE:-selena} --heat $${HEAT:-2}

boldness-ladder:
	python3 tools/boldness.py --ladder

boldness-rank:
	python3 tools/boldness.py --rank $${FILE:-variants.jsonl}

fabric:
	python3 tools/fabric.py --for $${HEROINE:-selena}

fabric-list:
	python3 tools/fabric.py --list

neg:
	python3 tools/neg_audit.py --check "$${NEG:-lowres, nsfw, nude}"

neg-scan:
	python3 tools/neg_audit.py --scan $${PATH:-assets/prompts}

repair:
	python3 tools/artifact_repair.py --fix-all assets/raw --out-dir assets/sprite

repair-report:
	python3 tools/artifact_repair.py --report $${RAW:-assets/raw/m_selena_raw.png}

mature:
	python3 tools/maturity.py --status

mature-on:
	python3 tools/maturity.py --verify-age && python3 tools/maturity.py --mode mature

green-on:
	python3 tools/maturity.py --mode green

audit:
	python3 -m automation.filter_audit --audit

audit-recipe:
	python3 -m automation.filter_audit --recipe

arena-plan:
	python3 -m automation.arena_loop plan --agents $${AGENTS:-16}

arena-init:
	python3 -m automation.arena_loop init --heroine $${HEROINE:-selena} --heat $${HEAT:-2} \
		--agents $${AGENTS:-16} --model $${MODEL:-illustrious} --reject-reason "$${REASON:-ушло в комикс}"

arena-next:
	python3 -m automation.arena_loop next

arena-status:
	python3 -m automation.arena_loop status

arena-winner:
	python3 -m automation.arena_loop winner

anchors:
	python3 tools/rig_anchors.py --all

slice:
	python3 tools/rig_anchors.py --all && python3 tools/build_slice.py

clean:
	rm -rf .pytest_cache __pycache__ automation/__pycache__ tests/__pycache__
