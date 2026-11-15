FROM nginx:1.28.3-alpine
COPY docker/nginx.conf /etc/nginx/nginx.conf.template
COPY docker/proxy-entrypoint.sh /proxy-entrypoint.sh
USER nginx
EXPOSE 8080
ENTRYPOINT ["sh", "/proxy-entrypoint.sh"]
