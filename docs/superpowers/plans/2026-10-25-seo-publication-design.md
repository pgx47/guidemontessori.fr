# Publication, SEO et accueil

Direction validée : crème, sauge, terracotta ; actualités visibles et datées, parcours par âge cliquables, URLs conservées.

- [x] Reproduire par unittest les paramètres API vides et les erreurs silencieuses ; corriger les valeurs par défaut et le code de sortie.
- [x] Remplacer l'accueil surchargé par un hero fixe, des liens par âge et les derniers guides et actualités.
- [x] Ajouter les liens Actualités au menu, améliorer navigation clavier, dates et dimensions des cartes.
- [x] Remplacer les dates système du sitemap par les dates éditoriales ; corriger l'article confondant tour rose et tour d'apprentissage.
- [x] Vérifier les tests Python, le build, les liens et métadonnées générés puis le rendu navigateur.
- [x] Commit, push et suivi du déploiement ; relancer la publication pour vérifier la correction réelle.

Vérifications : `.venv/bin/python -m unittest discover -s scripts/tests -v`, `npm run build`, inspection HTML du dossier dist et navigateur local.

Revue du diff : aucun problème important identifié. Image WebP : 99 872 octets au lieu de 727 460 octets.

Publication réelle confirmée : guide tour-observation-montessori-age-stabilite, puis relecture et correction des affirmations non sourcées avant validation finale. Consignes du générateur renforcées.
