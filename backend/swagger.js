const swaggerJSDoc = require('swagger-jsdoc');

const swaggerDefinition = {
  openapi: '3.0.3',
  info: {
    title: 'smup-unpad API',
    version: '1.0.0',
    description: 'Express API with Prisma database and Swagger documentation for smup-unpad'
  },
  servers: [
    {
      url: process.env.API_BASE_URL || 'http://localhost:4000',
      description: 'Local development server'
    }
  ],
  components: {
    schemas: {
      User: {
        type: 'object',
        properties: {
          id: { type: 'integer' },
          name: { type: 'string' },
          role: { type: 'string' },
          createdAt: { type: 'string', format: 'date-time' }
        }
      },
      ChatMessage: {
        type: 'object',
        properties: {
          id: { type: 'integer' },
          userId: { type: 'integer' },
          sender: { type: 'string' },
          role: { type: 'string' },
          content: { type: 'string' },
          createdAt: { type: 'string', format: 'date-time' }
        }
      }
    }
  }
};

const options = {
  definition: swaggerDefinition,
  apis: ['./server.js']
};

module.exports = swaggerJSDoc(options);
