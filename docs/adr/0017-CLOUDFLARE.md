# ADR-0017 — 
- **Statut :** Accepté  
- **Date :** 2026-11-23
- **Demande concernée :** §4.6

## Contexte
Le patron a entendu dire qu'il pourrait être pertinent de sécuriser la plateforme avec un certificat SSL. Puisque ce n'est pas dans notre définition de tâche il nous propose un bonus pour le faire.  

## Décision
Utiliser un tunnel Cloudflare couplé avec un certificat SSL sur NGINX.

## Options écartées
- **Accès direct par DNS vers EC2 :**
    Cette solution dépend de l'IP de l'EC2, nous ne voulions pas avoir des coûts supplémentaires et payer pour une Elastic IP.


## Conséquences
Nous avions déjà utilisé cette méthode par le passé, c'était plus simple et naturel à implémenter pour nous. Par ailleurs, le trafic bénéficie des règles de protection offertes par Cloudflare. L'ip de l'EC2 peut changer, cela ne nous impacte pas. Aucun port pour l'accès au site web n'est nécessaire, nous avons tout de même ouvert le 443 et 80 qui redirigent vers le tunnel. Cependant, le site dépend de Cloudflare, si ce dernier plante nous n'avons plus accès à l'application.