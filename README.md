# Cloud Based Video Streaming Platform
## Note: This project has been taken down to avoid AWS costs. Contact Shane if you would like a code walkthrough.


This is a project built for Emerging Production Techniques.
It uses Angular + Typescript, Java + Spring Boot connected with AWS to create a cloud based streaming platform.

The frontend is hosted on Cloudfront Pages, the API on Heroku and the remaining components on AWS.

Each component is broken up into the following directories:
- app: Angular App
- api: Java App
- db: PostgreSQL in docker for local db
- lambda: The lambda function in Python