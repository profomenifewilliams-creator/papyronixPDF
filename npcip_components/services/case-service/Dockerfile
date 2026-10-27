FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /src
COPY pom.xml .
COPY src ./src
RUN mvn -q -DskipTests package
FROM eclipse-temurin:21-jre
WORKDIR /app
RUN useradd --system --uid 10001 npcipsvc && mkdir -p /app/data && chown -R npcipsvc:npcipsvc /app
COPY --from=build /src/target/case-service-0.1.0.jar /app/app.jar
USER npcipsvc
EXPOSE 8081
ENTRYPOINT ["java","-XX:MaxRAMPercentage=75.0","-jar","/app/app.jar"]
