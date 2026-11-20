FROM nginx:1.28.3-alpine
COPY infra/nginx.prod.conf /etc/nginx/nginx.conf.template
COPY infra/proxy-entrypoint.sh /proxy-entrypoint.sh
USER nginx
EXPOSE 8080 8081
ENTRYPOINT ["sh", "/proxy-entrypoint.sh"]
