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

À cette vérification initiale, les correctifs n'étaient pas déployés sur Oracle.
Ils ne valident aucune
stratégie, aucun rendement ni aucun accès courtier. Aucun compte, clé, ordre
ou historique opérationnel n'a été modifié pendant leur vérification.

L'empreinte du code de recherche change : un plan de l'ancienne version devra
faire l'objet d'une nouvelle revue avant reprise, conformément au contrôle
existant `implementation_changed_new_plan_required`. Les preuves et fenêtres
consommées restent conservées. Préparer cette reprise avant un déploiement.

### État opérationnel relu le 4 octobre 2026

La lecture Oracle à 00:36 UTC confirme encore le code `557510a`, un profil et
un plan octobre figé, sans candidate sélectionnée ni fenêtre consommée. L'empreinte
de ce plan (`60bbc99…`) diffère de celle du code corrigé (`9c159f8…`). Un déploiement
conserverait le registre et les preuves, mais le calcul quotidien renverrait
`implementation_changed_new_plan_required`. Il ne reprendrait donc pas les
recherches de ce plan automatiquement. Sans candidate sélectionnée, un nouveau
plan mensuel peut être créé en novembre ; une reprise anticipée doit passer par
un mécanisme explicite de nouveau plan conservant l'ancien pour audit. Aucune
réinitialisation ni activation opérationnelle n'a été effectuée.

Restent les prérequis de `RETURN_CHECKLIST.md` : choix des instruments et du
compte papier, identifiants privés, données vérifiées, exécuteur prospectif,
recette papier et observation future. Le réel reste désactivé.

### Reprise explicite ajoutée et vérifiée à 02:01 UTC

Le blocage de reprise décrit plus haut dispose désormais d'une procédure
explicite : [`RESEARCH_RESUME.md`](RESEARCH_RESUME.md). Le parent sans candidate
ni contrôle réservé est conservé ; la nouvelle révision utilise un gel réel et
demande 126 séances entièrement postérieures. Aperçu par défaut, empreinte du
parent requise, verrou worker, transaction et refus des états incertains.
Le déploiement vérifie aussi la configuration Compose privée avant toute copie
active et toute activation, puis conserve ses contrôles Docker/API postérieurs.

- Suite locale : **100 tests, succès, 3 ignorés** (pandas absent).
- Suite Oracle isolée dans l'image Freqtrade épinglée ci-dessus : **100 tests,
  succès, aucun ignoré**, 3,134 secondes. Mêmes limites réseau/ressources et
  aucun montage de production. Paquet de 48 fichiers publics/Python, SHA-256
  `a6c30f75ed9f6be3a60b238f3515a68c534efb10f5cd5feed1256acca23b26ce`.
- Aperçu Oracle en lecture seule : reconstruction exacte du bundle ancien et
  des métadonnées réussie, 721 séances de développement, zéro fenêtre consommée.

Ces vérifications précèdent le déploiement et la décision de reprise. Elles ne
valident aucune stratégie ni rentabilité. La recette papier et l'observation
prospective restent à faire.

### Déploiement et reprise constatés à 02:07:09 UTC

- Commit opérationnel `e01d8ed06bac166205a8cc2ec732377383a0c329` publié sur
  `main`, déployé par le mécanisme existant après revue et aperçu legacy réussi.
  Prévalidation Compose privée passée, avant activation et relue après.
- Sauvegarde cohérente privée du registre, permissions 0600 :
  `/home/ubuntu/trading-releases/state-before-20261004T020421Z`.
  Snapshot du code précédent :
  `/home/ubuntu/trading-releases/previous-20261004T020503Z`.
- Parent relu juste avant la décision : figé, aucune candidate ni résultat,
  zéro fenêtre consommée, identique à la sauvegarde. Nouvel aperçu réussi à
  02:05:59 UTC, empreinte attendue vérifiée puis décision explicite appliquée.
- Révision `480cf13c30f9a23f`, gel réel
  `2026-10-04T02:06:02.168577+00:00`. Parent `superseded`, JSON du plan et résultat
  exactement conservés ; ancien événement conservé. Registre : deux plans,
  deux événements, zéro fenêtre consommée. Aucun état supprimé/réinitialisé.
- Aucun candidat n'a passé le développement. Les 126 séances de contrôle,
  si une candidate est ultérieurement sélectionnée selon le protocole, devront
  être entièrement postérieures au gel de leur plan. Aucune validation future
  n'est attribuée aux observations déjà vues.
- Worker existant exécuté : marqueur quotidien et rapport pointent la révision,
  état `no_candidate_passed_development`, erreurs vides, profil `research_only`.
- Les deux conteneurs sont sains, timer actif et activé au démarrage. API moteur
  confirmée `dry_run=true`, `running`, `spot`, identifiants exchange absents.
  Aucun compte, ordre réel ou clé exchange ajouté. Dossier de tests temporaire
  supprimé, aucun téléchargement d'image.

La mise à jour documentaire postérieure au déploiement ne change pas le code
opérationnel ci-dessus. Restent la recette papier et les observations futures,
ainsi que les prérequis privés de `RETURN_CHECKLIST.md`.
