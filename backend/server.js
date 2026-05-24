require('dotenv').config();
const express = require('express');
const cors = require('cors');
const axios = require('axios');
const swaggerUi = require('swagger-ui-express');
const swaggerSpec = require('./swagger');
const { PrismaClient } = require('@prisma/client');

const prisma = new PrismaClient();
const app = express();
const port = process.env.PORT || 4000;
const geminiUrl = process.env.GEMINI_API_URL || 'https://api.openai.com/v1/responses';
const geminiModel = process.env.GEMINI_MODEL || 'gemini-1.5';

app.use(cors());
app.use(express.json());

const roleValues = ['GUEST', 'STUDENT', 'TEACHER', 'ADMIN'];

async function sendToGemini(prompt) {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    throw new Error('Missing GEMINI_API_KEY in environment');
  }

  const payload = {
    model: geminiModel,
    input: prompt
  };

  const response = await axios.post(geminiUrl, payload, {
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json'
    }
  });

  const data = response.data;
  if (typeof data.output_text === 'string') {
    return data.output_text;
  }

  if (Array.isArray(data.output) && data.output.length > 0) {
    const content = data.output[0].content;
    if (Array.isArray(content) && content.length > 0) {
      return content[0].text || '';
    }
  }

  if (Array.isArray(data.choices) && data.choices.length > 0) {
    return data.choices[0]?.message?.content?.[0]?.text || data.choices[0]?.text || '';
  }

  return JSON.stringify(data);
}

/**
 * @openapi
 * /api/health:
 *   get:
 *     summary: Health check endpoint
 *     responses:
 *       200:
 *         description: Service is healthy
 *         content:
 *           application/json:
 *             schema:
 *               type: object
 *               properties:
 *                 status:
 *                   type: string
 *                 timestamp:
 *                   type: string
 */
app.get('/api/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

/**
 * @openapi
 * /api/roles:
 *   get:
 *     summary: Get available user roles
 *     responses:
 *       200:
 *         description: Role list
 *         content:
 *           application/json:
 *             schema:
 *               type: object
 *               properties:
 *                 data:
 *                   type: array
 *                   items:
 *                     type: string
 */
app.get('/api/roles', (req, res) => {
  res.json({ data: roleValues });
});

/**
 * @openapi
 * /api/users:
 *   get:
 *     summary: Get all users
 *     responses:
 *       200:
 *         description: List of users
 *   post:
 *     summary: Create a new user profile
 *     requestBody:
 *       required: true
 *       content:
 *         application/json:
 *           schema:
 *             type: object
 *             properties:
 *               name:
 *                 type: string
 *               role:
 *                 type: string
 *     responses:
 *       201:
 *         description: Created user profile
 */
app.get('/api/users', async (req, res, next) => {
  try {
    const users = await prisma.user.findMany({ orderBy: { createdAt: 'asc' } });
    res.json({ data: users });
  } catch (error) {
    next(error);
  }
});

app.post('/api/users', async (req, res, next) => {
  try {
    const { name, role } = req.body;
    if (!name || typeof name !== 'string' || !roleValues.includes(role)) {
      return res.status(400).json({ error: 'name and valid role are required' });
    }

    const user = await prisma.user.create({
      data: { name, role }
    });

    res.status(201).json({ data: user });
  } catch (error) {
    next(error);
  }
});

/**
 * @openapi
 * /api/chat/history:
 *   get:
 *     summary: Get chat history for a user
 *     parameters:
 *       - in: query
 *         name: userId
 *         schema:
 *           type: integer
 *     responses:
 *       200:
 *         description: Chat history returned
 */
app.get('/api/chat/history', async (req, res, next) => {
  try {
    const userId = req.query.userId ? Number(req.query.userId) : undefined;
    const messages = await prisma.chatMessage.findMany({
      where: userId ? { userId } : undefined,
      orderBy: { createdAt: 'asc' }
    });
    res.json({ data: messages });
  } catch (error) {
    next(error);
  }
});

/**
 * @openapi
 * /api/chat:
 *   post:
 *     summary: Send a chat message and receive a Gemini response
 *     requestBody:
 *       required: true
 *       content:
 *         application/json:
 *           schema:
 *             type: object
 *             properties:
 *               userId:
 *                 type: integer
 *               content:
 *                 type: string
 *     responses:
 *       201:
 *         description: Chat response created
 */
app.post('/api/chat', async (req, res, next) => {
  try {
    const { userId, content } = req.body;
    if (!content || typeof content !== 'string') {
      return res.status(400).json({ error: 'content is required and must be a string' });
    }

    const user = userId
      ? await prisma.user.findUnique({ where: { id: Number(userId) } })
      : null;

    if (!user) {
      return res.status(404).json({ error: 'user not found' });
    }

    const userMessage = await prisma.chatMessage.create({
      data: {
        userId: user.id,
        sender: 'user',
        role: user.role,
        content
      }
    });

    const assistantPrompt = `You are the SMUP UNPAD assistant chatting with a ${user.role.toLowerCase()} named ${user.name}. Respond formally and clearly. User message: ${content}`;
    const assistantText = await sendToGemini(assistantPrompt);

    const botMessage = await prisma.chatMessage.create({
      data: {
        userId: user.id,
        sender: 'bot',
        role: user.role,
        content: assistantText || 'Maaf, terjadi kesalahan. Silakan coba lagi.'
      }
    });

    res.status(201).json({ data: { userMessage, botMessage } });
  } catch (error) {
    next(error);
  }
});

app.use('/api-docs', swaggerUi.serve, swaggerUi.setup(swaggerSpec));

app.use((err, req, res, next) => {
  console.error(err);
  res.status(500).json({ error: 'internal_server_error' });
});

app.listen(port, () => {
  console.log(`🚀 Backend running on http://localhost:${port}`);
  console.log(`📄 Swagger docs available at http://localhost:${port}/api-docs`);
});
