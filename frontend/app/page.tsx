'use client';

import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';

const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:4000';

const roles = [
  { value: 'GUEST', label: 'Guest' },
  { value: 'STUDENT', label: 'Student' },
  { value: 'TEACHER', label: 'Teacher' },
  { value: 'ADMIN', label: 'Admin' }
];

const presetQuestions = [
  'What programs are available at SMUP UNPAD?',
  'How can I register for classes?',
  'What are the campus opening hours?',
  'Where can I get help with administration?',
  'How do I contact the support team?'
];

type ChatMessage = {
  id: number;
  userId?: number;
  sender: 'user' | 'bot';
  role: string;
  content: string;
  createdAt: string;
};

type User = {
  id: number;
  name: string;
  role: string;
};

export default function HomePage() {
  const [name, setName] = useState('');
  const [role, setRole] = useState('GUEST');
  const [user, setUser] = useState<User | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [status, setStatus] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [showPresets, setShowPresets] = useState(false);
  const [greetingShown, setGreetingShown] = useState(false);
  const chatEndRef = useRef<HTMLDivElement | null>(null);

  const greeting = useMemo(
    () =>
      `Halo ${name || 'tamu'}! Saya asisten virtual SMUP UNPAD untuk ${role.toLowerCase()}.
Silakan pilih preset pertanyaan atau ketik pesan Anda.`,
    [name, role]
  );

  useEffect(() => {
    if (chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isTyping]);

  async function createUserProfile() {
    if (!name.trim()) {
      setStatus('Please enter your name before starting the chat.');
      return null;
    }

    try {
      const response = await axios.post(`${apiUrl}/api/users`, { name: name.trim(), role });
      const createdUser = response.data.data;
      setUser(createdUser);
      setStatus('Welcome! Your chat profile is ready.');
      if (!greetingShown) {
        setMessages([
          {
            id: -1,
            sender: 'bot',
            role: 'ADMIN',
            content: greeting,
            createdAt: new Date().toISOString()
          }
        ]);
        setGreetingShown(true);
      }
      return createdUser;
    } catch (error) {
      setStatus('Unable to create user profile. Please try again.');
      return null;
    }
  }

  async function startChat(event: FormEvent) {
    event.preventDefault();
    const createdUser = user || (await createUserProfile());
    if (!createdUser) return;

    if (!greetingShown) {
      setMessages([
        {
          id: -1,
          sender: 'bot',
          role: 'ADMIN',
          content: greeting,
          createdAt: new Date().toISOString()
        }
      ]);
      setGreetingShown(true);
    }
  }

  async function handleSendMessage(message?: string) {
    const content = message ?? inputValue.trim();
    if (!content) return;
    if (!user) {
      setStatus('Please choose a name and role before sending a message.');
      return;
    }

    setInputValue('');
    setStatus('');
    setIsTyping(true);

    const userMessage: ChatMessage = {
      id: Date.now(),
      userId: user.id,
      sender: 'user',
      role: user.role,
      content,
      createdAt: new Date().toISOString()
    };
    setMessages((prev) => [...prev, userMessage]);

    try {
      const response = await axios.post(`${apiUrl}/api/chat`, {
        userId: user.id,
        content
      });
      const { userMessage: savedUser, botMessage } = response.data.data;
      setMessages((prev) => [...prev.filter((m) => m.id !== userMessage.id), savedUser, botMessage]);
      setStatus('');
    } catch (error) {
      setStatus('Bot tidak merespon. Silakan coba lagi.');
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now() + 1,
          sender: 'bot',
          role: 'bot',
          content: 'Maaf, terjadi kesalahan saat menghubungkan ke layanan chatbot.',
          createdAt: new Date().toISOString()
        }
      ]);
    } finally {
      setIsTyping(false);
    }
  }

  return (
    <main className="chat-container">
      <section className="chat-panel">
        <div className="chat-header">
          <div>
            <p className="chat-label">SMUP UNPAD Chatbot</p>
            <h1>Role-based chatbot</h1>
          </div>
          <div className="role-pill">{role}</div>
        </div>

        <form className="profile-form" onSubmit={startChat}>
          <div className="input-row">
            <div className="input-group">
              <label>Name</label>
              <input value={name} onChange={(event) => setName(event.target.value)} placeholder="Your full name" />
            </div>
            <div className="input-group">
              <label>Role</label>
              <select value={role} onChange={(event) => setRole(event.target.value)}>
                {roles.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <button type="submit" className="primary-button">
            Start Chat
          </button>
        </form>

        <div className="chat-window">
          <div className="chat-bubbles">
            {messages.map((message) => (
              <div key={`${message.id}-${message.createdAt}`} className={`bubble ${message.sender === 'user' ? 'bubble-user' : 'bubble-bot'}`}>
                <div className="bubble-meta">
                  <span>{message.sender === 'user' ? 'You' : 'SMUP Bot'}</span>
                  <span>{new Date(message.createdAt).toLocaleTimeString()}</span>
                </div>
                <p>{message.content}</p>
              </div>
            ))}
            {isTyping ? (
              <div className="bubble bubble-bot typing-bubble">
                <div className="bubble-meta">
                  <span>SMUP Bot</span>
                </div>
                <div className="typing-indicator">
                  <span />
                  <span />
                  <span />
                </div>
              </div>
            ) : null}
            <div ref={chatEndRef} />
          </div>
        </div>

        <div className="preset-card">
          <p>Preset questions</p>
          <div className="preset-list">
            {presetQuestions.map((question) => (
              <button key={question} type="button" onClick={() => handleSendMessage(question)}>
                {question}
              </button>
            ))}
          </div>
        </div>

        <div className="chat-input-area">
          <textarea
            value={inputValue}
            onChange={(event) => setInputValue(event.target.value)}
            placeholder="Type your question here..."
            rows={2}
          />
          <button type="button" className="primary-button" onClick={() => handleSendMessage()}>
            Send
          </button>
        </div>

        {status ? <div className="status-message">{status}</div> : null}
      </section>
    </main>
  );
}
