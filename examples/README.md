# Public synthetic examples

`curriculum/math-mp-reduction.md` is an original, synthetic MP-style source. It is not an official curriculum. Run `uv run hermes-edu ingest --example` to index it for a first local TD run. Generated examples are stored under `workspace/` and are not committed.

`wording/transitions-cpge.fr.txt` contient 30 expressions de liaison attestées dans six chapitres de Garcin, Prost et Vienney. Le fichier `.sources.json` associé donne les pages PDF, les normalisations et les empreintes des documents (les chapitres de Vienney sont MP2I). Utiliser `hermes-edu course ... --phrases-file examples/wording/transitions-cpge.fr.txt` pour activer l'adaptation des exemples et des réponses aux exercices. Les explications et formules restent protégées ; la vérification peut refuser une liaison qui change le sens.
