# Fiabilité du site et intégrations

Demande : jours fixes, vérifier le fonctionnement du site, l'affiliation Amazon et les statistiques.

- Remplacer le tirage aléatoire des guides par lundi, mercredi et vendredi ; conserver les actualités mercredi et samedi.
- Corriger les trois destinations internes inexistantes et vérifier toutes les pages et liens internes.
- Unifier le tag Amazon mtssri-21, ajouter sponsored aux liens MDX et contrôler les redirections historiques.
- Vérifier les filtres cadeaux et annuaire, le chargement GA4 et l'accès effectif aux rapports.
- Diagnostiquer les intégrations Google via le compte de service existant, sans afficher de données privées dans les logs publics.
- Exécuter les tests et le build, revue du diff puis déploiement et vérification en production.

État initial : 122 pages du sitemap en HTTP 200 ; trois liens éditoriaux internes en 404 ; 286 liens Amazon directs avec le bon tag, dont 65 sans sponsored ; 17 liens courts à vérifier.

## Corrections et validation

- Guides : lundi, mercredi, vendredi à 6 h UTC ; actualités mercredi et samedi à 7 h UTC.
- Trois liens internes corrigés à la source, avec redirections permanentes pour leurs anciennes URL déjà connues de Google.
- Dix-sept redirections Amazon historiques résolues ; destinations réelles conservées avec le tag du site. Un ASIN manifestement fictif dans un ancien guide a été remplacé par une recherche Amazon descriptive.
- Tag centralisé et attribut sponsored appliqué au rendu MDX, y compris les liens HTML historiques. Les cartes utilisent la même configuration.
- Soumission du sitemap via Search Console au lieu de l'API Indexing destinée aux offres d'emploi et vidéos en direct. Échec visible mais non bloquant pour le déploiement.
- Contrôle avant publication/déploiement : 132 pages construites, 411 liens Amazon, aucun lien interne manquant et aucun défaut de tag ou sponsored.
- Trois tests JavaScript et huit tests Python réussis. Revue indépendante du diff sans problème important.
- Filtres cadeaux, carte et recherche d'écoles vérifiés dans le navigateur. Google Analytics et Search Console consultés en session authentifiée ; aucune donnée privée de fréquentation n'est copiée dans ce dépôt public.
- Rapports de commissions Amazon inaccessibles sans connexion au compte Partenaires : aucune conclusion sur les ventes ou rémunérations.
