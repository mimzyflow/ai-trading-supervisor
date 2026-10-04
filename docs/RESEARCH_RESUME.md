# Reprise explicite après modification du code

La reprise conserve le plan parent, son JSON et son résultat, tous les événements
et toutes les fenêtres consommées. Elle crée une révision de développement avec
un nouveau gel réel après le calcul. Elle ne crée aucun ordre ni accès courtier.
Les 126 séances de contrôle doivent fermer strictement après ce nouveau gel.
Les observations déjà disponibles servent uniquement au développement.

## Préconditions et refus

Seul un parent `frozen`, sans candidate sélectionnée, résultat ni fenêtre de
contrôle déjà réservée, peut reprendre. Le profil reste `research_only` et la
configuration publique doit passer les contrôles DRY-RUN Kraken EUR existants.
Le code doit avoir changé. Un plan concurrent, un état incomplet, une fenêtre
incohérente ou un worker actif provoquent un refus, sans réinitialisation.

Pour un plan récent, le préfixe historique et toutes les caractéristiques des
instruments doivent correspondre à son empreinte figée. Pour un plan ancien
sans cette empreinte, le programme reconstruit exactement le bundle complet à
son gel initial, métadonnées globales et instruments inclus. Son hash doit être
identique au `data_sha256` original. `legacy_frozen_bundle_unverifiable` impose
de conserver le refus : aucune approximation ni option de contournement.

## Aperçu puis décision

Dans le projet Oracle, avec les droits existants sur le registre privé :

```sh
sudo -n python3 -m research_lab.resume --parent-epoch '<identifiant-parent>'
```

Cette commande ouvre la base en lecture seule et prend le verrou existant du
worker. Elle ne crée aucun fichier d'état. Après un aperçu réussi, utiliser le
hash parent affiché pour la décision explicite :

```sh
sudo -n python3 -m research_lab.resume --parent-epoch '<identifiant-parent>' \
  --apply --expected-parent-sha256 '<empreinte-aperçu>'
```

Le verrou et une transaction `BEGIN IMMEDIATE` protègent la revalidation, le
nouveau plan, le statut `superseded` du parent et l'événement de décision. Un
échec restaure la transaction entière. Le JSON du parent et son résultat sont
inchangés. Il n'existe aucune option CLI permettant de dater le gel dans le
passé. Le cache quotidien reconnaît le parent remplacé au prochain cycle ;
aucun marqueur ne doit être supprimé. Une deuxième application au même parent
est refusée.

## Déploiement sûr et vérification

1. Tests et revue du code ; aperçu candidat sur le registre existant.
2. Sauvegarde SQLite privée cohérente par l'API `backup`, permissions 0600,
   conservée hors Git ; relever parent, résultat et compte des fenêtres.
3. Commit, push, puis mécanisme `scripts/deploy-oracle.sh` existant. Le candidat
   Compose résolu est capturé en mémoire privée avant toute copie active ; mode
   DRY-RUN et clés exchange absentes/vides sont obligatoires. Chaque activation
   ou restauration repasse ce contrôle avant `compose up` et reprise du timer.
4. Vérifier build-info, santé Docker/API, mode DRY-RUN et absence de clés. Refaire
   l'aperçu, relire absence de candidate/fenêtre du parent, puis appliquer avec
   son empreinte attendue. Le déploiement seul ne remplace aucun plan.
5. Vérifier JSON/résultat parent conservés, fenêtres et anciens événements
   conservés, révision et heure du gel, nouveau marqueur, timer et rapport.

Le rollback restaure du code et conserve les données. Ne jamais restaurer une
ancienne base pour faire disparaître une décision, une preuve ou une fenêtre.
Si le code restauré ne correspond plus à la révision, le garde de code refuse
son contrôle futur jusqu'à une reprise revue. Aucune rentabilité ou stratégie
validée ne découle de cette procédure.

## Vérification du 4 octobre 2026

À 02:01:08 UTC, l'aperçu candidat sur Oracle a réussi par reconstruction exacte
du bundle ancien : `legacy_complete_bundle_sha256`, 721 séances, zéro fenêtre
consommée. Le parent octobre était figé, sans candidate ni résultat. Son
empreinte d'aperçu était
`2c6a6647aaaf566b46df2c2110e709c839554fdc07b8c36d12d9f4ffa19b97a6`.
Cette observation précède la décision et ne prouve aucune activation.

Le commit `e01d8ed` a ensuite été déployé par le mécanisme existant. L'aperçu a
été refait à 02:05:59 UTC, le parent comparé exactement à la sauvegarde privée,
puis la décision explicite a créé la révision `480cf13c30f9a23f` à
`2026-10-04T02:06:02.168577+00:00`. Vérification à 02:07:09 UTC : parent JSON et
résultat conservés, anciens événements conservés, deux plans, deux événements,
zéro fenêtre consommée. Aucune candidate ne passe le développement. Marqueur
et rapport pointent la révision, sans erreur. Deux conteneurs sains, timer
actif/activé et API DRY-RUN spot en fonctionnement, aucune clé exchange injectée.
