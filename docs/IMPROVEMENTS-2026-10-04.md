# Correctifs de reprise du 4 octobre 2026

Base examinée : `557510ab6618f2d768d513713c1528a293c8e3d8`.
Travail isolé dans la branche `codex/improvements-20261004`.

## Changements

1. **Historique de développement figé.** Le plan mémorise le nombre de bougies
   et une empreinte du préfixe historique, avec les caractéristiques des
   instruments. La recherche vérifie cette empreinte avant de réserver ou
   d'évaluer le contrôle futur. Une révision des prix, volumes, splits, lots ou
   une troncature refuse le contrôle. L'ajout de nouvelles séances reste permis.
   Un ancien plan dépourvu de cette preuve ne reçoit pas de validation implicite.
2. **Marqueurs quotidiens récupérables.** Un marqueur illisible ou mal formé
   produit une erreur assainie ; la collecte et le rapport peuvent continuer.
   La récupération conserve la base, les événements et les fenêtres réservées.
   Si les données manquent aussi, le rapport indique leur indisponibilité.
3. **Arrêt mémorisé retenté.** Une erreur d'arrêt reste visible séparément de
   l'observation. Le cycle suivant retente un arrêt déjà enregistré, y compris
   avec une télémétrie illisible. Chaque tentative repasse par les vérifications
   actuelles Docker/API, uniquement sur le conteneur confirmé DRY-RUN. Sans arrêt
   enregistré et sans observation valide, aucune commande Docker n'est tentée.

## Vérifications locales

- `python3 -m unittest discover -s tests` : **80 tests, succès, 3 ignorés**.
  Sept tests ajoutés couvrent les révisions de données, l'ajout légitime de
  séances, les anciens plans sans empreinte, la récupération des marqueurs,
  la conservation des preuves et la reprise d'arrêt. Les réponses de simulation,
  Docker et API utilisées dans ces régressions sont fictives.
- `python3 -m compileall -q research_lab supervisor scripts tests user_data/strategies` : succès.
- `python3 scripts/check_simulation.py` : succès.
- `git diff --check` : succès.

Les trois tests ignorés demandent pandas, absent du Python système local.
Docker n'est pas installé sur ce Mac. Le Python embarqué répond en version
3.12.14, mais son contrôle d'import pandas n'a pas terminé et a été interrompu.
Aucun paquet n'a été installé.

## Vérification dans l'image Freqtrade existante

La suite a aussi été exécutée sur Oracle, dans un conteneur de test isolé :
**80 tests, succès, aucun test ignoré**, en 1,238 seconde.

- Image déjà présente et digest vérifié :
  `freqtradeorg/freqtrade:2026.9@sha256:9d67afb8eb5f4e1210f4fb067efcbd5e005bd4f1c27f6f3888b8b9fc7f9b5199`.
- Paquet : 45 fichiers Python et configurations publiques sélectionnés,
  empreinte SHA-256
  `d483a4d34174f9277cf6908221c1ba868904610d35e4f7040023578e5d98f2f3`.
- Réseau désactivé, conteneur supprimé en sortie, CPU 0,5, mémoire 256 Mo,
  32 processus maximum, aucune capacité Linux, aucun nouveau privilège.
- Système de fichiers en lecture seule, espace temporaire dédié. Le seul
  montage est la copie temporaire du code en lecture seule. Aucun volume de
  production, base, secret, environnement hôte ou socket Docker n'est exposé.
- Le dossier temporaire Oracle a été supprimé après le test. Aucun service
  opérationnel n'a été modifié et aucune image n'a été téléchargée.

## Limites et reprise

Ces correctifs n'ont pas été déployés sur Oracle. Ils ne valident aucune
stratégie, aucun rendement ni aucun accès courtier. Aucun compte, clé, ordre
ou historique opérationnel n'a été modifié pendant leur vérification.

L'empreinte du code de recherche change : un plan de l'ancienne version devra
faire l'objet d'une nouvelle revue avant reprise, conformément au contrôle
existant `implementation_changed_new_plan_required`. Les preuves et fenêtres
consommées restent conservées. Préparer cette reprise avant un déploiement.

Restent les prérequis de `RETURN_CHECKLIST.md` : choix des instruments et du
compte papier, identifiants privés, données vérifiées, exécuteur prospectif,
recette papier et observation future. Le réel reste désactivé.
