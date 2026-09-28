# Création de cours

Hermes crée des cours à partir d'un programme indexé et de références PDF. La commande embarque un workflow LangGraph réel : recherche du programme, plan, approbation, recherche par section, génération, audit, révisions ciblées, LaTeX et PDF.

## Préparer les sources

Télécharger le programme auprès de l'autorité concernée, puis l'indexer en conservant son URL officielle. Le nom du curriculum est explicite : il distingue notamment MP France et MP Maroc. Une étiquette `curriculum` ne garantit pas à elle seule l'authenticité d'un document.

```bash
uv run hermes-edu ingest data/programme-mp.pdf \
  --source-id programme-mp --title "Programme officiel MP" \
  --curriculum mp-maroc --track MP --kind curriculum \
  --source-url "https://autorite.example/programme-mp.pdf"
uv run hermes-edu references add-directory data/mes-cours
uv run hermes-edu curriculum search "intégrales dépendant d'un paramètre" \
  --curriculum mp-maroc --track MP --top-k 8
```

La recherche calcule l'embedding de la question avec le même modèle que celui des documents, puis interroge les passages filtrés par curriculum, filière, matière et type. La bibliothèque PDF utilise son index HNSW ; les programmes utilisent le magasin SQLite existant. Les passages, scores et identifiants sont conservés. L'absence de source pertinente arrête la génération avec un message explicite.

## Du programme à chaque section

1. Retrouver la partie du programme officiel correspondant au sujet demandé.
2. En extraire un plan : chaque section doit déclarer les identifiants des passages officiels qui la fondent. Un identifiant inconnu ou absent est rejeté pour un nouveau plan.
3. Pour chaque titre, construire une requête avec le sujet, l'objectif et la sous-partie officielle correspondante, puis rechercher dans les références après embedding. La requête est limitée à 4 000 caractères et réserve de la place au passage officiel. La recherche interroge le même index HNSW avec une passe générale puis une passe filtrée sur les blocs d'exemples, afin de ne pas laisser les définitions ou théorèmes évincer tous les exemples disponibles. `HERMES_RAG_TOP_K` règle la passe générale ; `HERMES_COURSE_EXAMPLE_TOP_K` règle le nombre de candidats d'exemples cherchés par section, 6 par défaut. Avant la rédaction, le LLM sélectionne les 0 à 3 exemples vraiment pertinents à partir de ces candidats et du résultat général précédent.
4. Rédiger la section à partir des passages de cours retrouvés, puis passer à la section suivante. Le programme guide le périmètre ; les identifiants internes des blocs mathématiques doivent venir des références pédagogiques.
5. Auditer les sections contre leurs sources conservées, corriger les sections concernées tant que le budget de révision le permet, puis produire le document. Si des erreurs persistent après le budget prévu, le workflow continue jusqu'au PDF et marque le résultat `audit_status=needs_revision` avec la liste des points à reprendre.

Les contextes du programme et des références sont sélectionnés séparément : un long passage officiel ne doit pas évincer les cours utilisés pour rédiger. Les anciens checkpoints sans identifiants de programme par section restent lisibles ; ils utilisent alors le contexte officiel borné déjà sauvegardé.

La rédaction demande des blocs lisibles : chaque étape de raisonnement et chaque phrase de liaison doit commencer dans un nouveau paragraphe. Quand l'option de phrases de liaison est active, l'adaptation insère aussi un saut de paragraphe avant une liaison remplacée si elle était accolée à la phrase précédente.

La même règle s'applique aux appels Python directs : `CreateCourse.generate(..., curriculum=...)` exige le contexte officiel en plus des passages pédagogiques. Un programme absent ou un passage officiel fourni comme référence pédagogique provoque une erreur. L'audit reçoit lui aussi la sous-partie officielle de la section concernée.

Un programme qui cite un chapitre comme prérequis ne fournit pas nécessairement son contenu détaillé. Il faut indexer le programme du niveau approprié pour obtenir un plan détaillé fidèle ; Hermès ne doit pas inventer les sous-parties manquantes.

## Créer et reprendre

```bash
uv run hermes-edu course "Intégrales dépendant d'un paramètre" \
  --curriculum mp-maroc --track MP --sections 6
uv run hermes-edu course-resume THREAD_ID approve
# Après un échec transitoire, reprendre uniquement le nœud restant :
uv run hermes-edu course-resume THREAD_ID continue
```

`--yes` lance directement la génération sans pause sur le plan. `--document-id ID` peut être répété pour limiter les références pédagogiques. `--tex-only` conserve le mode sans compilation lors des reprises. `course-resume THREAD_ID reject` termine un plan en attente sans générer de document. Chaque section achevée est sauvegardée ; elle n'est pas régénérée lors de la reprise d'une section suivante.

Après la dernière section, Hermès rend un brouillon TeX avant l'audit. Après les corrections et la vérification, ou après épuisement du budget de révision, il rend le TeX final puis le compile. Un quality gate déterministe produit ensuite `workspace/THREAD_ID/quality_report.json` et `quality_report.md`. Les sorties finales sont `workspace/THREAD_ID/course.tex`, `course.pdf` lorsque la compilation est demandée, et les rapports qualité. Le résultat JSON contient `audit_status`, `quality_status`, le rapport qualité, les points d'audit à reprendre, les sources internes, tokens, modèles, latences et coûts estimés. Les sources restent absentes du cours imprimé : elles servent à l'audit, au rapport et à la traçabilité interne, pas à une bibliographie visible. Les checkpoints gardent également les passages retrouvés et le contenu structuré. Les estimations de coût peuvent être inconnues si aucun tarif n'est configuré.

Si les références ne suffisent pas, Hermès signale un `source_gap` dans le rapport et marque le résultat `DRAFT`. Il ne doit pas écrire dans le cours des phrases du type "les références disponibles ne permettent pas..." ; ces messages appartiennent au workflow et au rapport qualité.

## Mathématiques et compilation

Le modèle renvoie des blocs structurés (définition, théorème, preuve, exemple, méthode, remarque, exercice, solution), jamais un document TeX libre. Les formules sont délimitées par `$...$` ou `$$...$$` et contrôlées par une liste explicite de commandes mathématiques autorisées. Les environnements et macros arbitraires sont rejetés. Le texte ordinaire est échappé.

XeLaTeX est le moteur par défaut. Le modèle de cours fonctionne aussi avec pdfLaTeX :

```bash
HERMES_LATEX_ENGINE=pdflatex uv run hermes-edu course ...
```

La compilation conserve les restrictions existantes : absence de shell escape, délai limité, confinement des fichiers, vérification du hash de la source et réouverture du PDF. Un code de sortie LaTeX nul ne suffit plus : les alertes critiques du log et le texte extrait du PDF sont inspectés pour repérer références indéfinies, glyphes manquants, macros visibles, underscores/carets mathématiques imprimés en texte brut et caractères de remplacement. Si la compilation échoue, le workflow peut lancer un nœud `repair_latex` borné par `HERMES_LATEX_REPAIR_LOOPS`. Ce nœud utilise uniquement des corrections déterministes par regex Python à partir des lignes signalées par le journal LaTeX ; il ne réécrit pas le contenu mathématique et ne fait pas appel au modèle. L'audit du contenu est une revue par modèle, pas une preuve formelle de correction mathématique. Consulter ADR 0016 pour les frontières et limites.

## Audit et corrections sur DeepInfra

Les tâches `audit` et `revise` peuvent utiliser un modèle différent de la rédaction. Exemple de configuration :

```dotenv
HERMES_AUDIT_PROVIDER=deepinfra
HERMES_AUDIT_MODEL=Qwen/Qwen3-235B-A22B-Instruct-2507
HERMES_REVISION_PROVIDER=deepinfra
HERMES_REVISION_MODEL=Qwen/Qwen3-Next-80B-A3B-Instruct
HERMES_MAX_OUTPUT_TOKENS=16000
HERMES_AUDIT_FALLBACK_MODELS=Qwen/Qwen3-Next-80B-A3B-Instruct,deepseek
HERMES_REVISION_FALLBACK_MODELS=Qwen/Qwen3-235B-A22B-Instruct-2507,deepseek
HERMES_PLAN_FALLBACK_MODELS=Qwen/Qwen3-Next-80B-A3B-Instruct,Qwen/Qwen3-235B-A22B-Instruct-2507
HERMES_GENERATION_FALLBACK_MODELS=Qwen/Qwen3-Next-80B-A3B-Instruct,Qwen/Qwen3-235B-A22B-Instruct-2507
```

Les listes `HERMES_AUDIT_FALLBACK_MODELS`, `HERMES_REVISION_FALLBACK_MODELS`, `HERMES_PLAN_FALLBACK_MODELS` et `HERMES_GENERATION_FALLBACK_MODELS` sont des CSV ordonnés d'au plus quatre candidats distincts, sans répéter le modèle préféré. Une sortie invalide, un délai ou une erreur passe au candidat suivant. `verify` utilise la même liste que `generate`; chaque révision décale le premier candidat modulo le nombre de candidats, sans modifier l'ordre configuré. Lorsqu'une tâche a des alternatives, chaque candidat DeepSeek ou DeepInfra reçoit une tentative de transport et une tentative de réponse vide avant le suivant. Chaque section est auditée séparément et sauvegardée ; après une correction, seule cette section est réauditée. Un audit contradictoire qui signale une erreur puis conclut par `No defect`, ou dont l'explication dépasse 2 000 caractères, est rejeté pour les nouvelles réponses, sans validation automatique. Les métriques locales dans `.local/llm-metrics.db` ne gardent ni prompts ni contenu : `SQLiteModelOutcomeStore.summary()` sert à examiner latence et validation avant toute recommandation manuelle, sans réordonner les modèles. Le coût agrégé est inconnu si un appel de la série n'a pas de coût connu.

## Fidélité aux références — règle de production

La création doit partir des passages réellement retrouvés après embedding de la demande. Les références ne sont pas un simple ajout bibliographique après rédaction : elles déterminent le contenu autorisé du cours.

- Conserver les hypothèses et les conclusions des définitions et théorèmes.
- Utiliser uniquement les preuves, exemples et exercices soutenus par les passages fournis ; ne pas inventer une preuve absente ou compléter de mémoire.
- Conserver les identifiants de passages et la provenance (document, pages ou URL officielle) pour l'audit et le résultat JSON, sans insérer de citations ni de bibliographie dans le cours rendu.
- Si les références ne suffisent pas, signaler la lacune et demander une source complémentaire au lieu d'inventer le contenu manquant.
- Auditer la fidélité aux références en plus de la correction mathématique. Une référence pertinente réduit le risque d'erreur ; elle ne garantit pas à elle seule qu'une reformulation du modèle soit exacte.

Les sections corrigées repassent par `verify`, qui hérite des candidats de `generate`. Le modèle DeepInfra reste configurable par tâche et ne devient pas le fournisseur général de la rédaction. La vérification par modèle reste distincte d'une validation mathématique formelle.

## Expressions de liaison imposées

Pour harmoniser les **exemples et réponses aux exercices**, fournir une liste UTF-8, une expression par ligne :

```bash
uv run hermes-edu course "Intégrales dépendant d'un paramètre" \
  --curriculum mp-maroc --track MP --sections 6 \
  --phrases-file examples/wording/transitions-cpge.fr.txt
```

La banque d'exemple comprend 30 expressions attestées ; `examples/wording/transitions-cpge.sources.json` précise leur provenance. La liste est extensible, jusqu'à 200 expressions et 20 000 caractères. Chaque remplacement est exactement une expression de la liste, sans paraphrase ni variante de casse automatique. Les entrées ne contiennent pas de formules.

Après l'audit, le nœud `adapt_wording` choisit les liaisons à remplacer dans les blocs `example` et `solution`. Python applique ces changements localisés et préserve à l'identique les formules `$...$`/`$$...$$`, leur ordre, les autres passages et les identifiants internes de provenance. `verify_wording` contrôle ensuite le sens et les liaisons restantes, même si le modèle propose de ne rien changer. En cas de refus ou d'altération du sens, le workflow abandonne cette adaptation locale, conserve le texte original, marque `wording.status=needs_revision`, puis continue vers le PDF. Les échecs transitoires du fournisseur restent reprenables. La reprise conserve la liste et son empreinte sauvegardées, sans relire le fichier.

Ces deux étapes utilisent DeepSeek dans la configuration courante. Elles ne réécrivent pas les énoncés, définitions, théorèmes ou preuves. Les contrôles des formules et des expressions insérées sont déterministes ; reconnaître toutes les liaisons et juger leur équivalence reste une vérification par modèle. Voir ADR 0018.

Les totaux du résultat JSON décrivent les appels sauvegardés avec des étapes terminées. Un appel ayant répondu avant l'échec d'un nœud peut n'apparaître que dans les journaux ; un délai réseau peut aussi laisser son coût inconnu. Ces totaux ne remplacent donc pas le relevé du fournisseur pour le suivi complet des dépenses.
