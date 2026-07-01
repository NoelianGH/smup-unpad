require('dotenv').config();
const mongoose = require('mongoose');
const bcrypt = require('bcrypt');
const { Admin } = require('./models/adminModel');

async function main() {
  await mongoose.connect(process.env.MONGO_URI);
  // Check if admin already exists
  const existing = await Admin.findOne({ username: 'admin' });
  if (existing) {
    console.log('Admin already exists. Skipping creation.');
  } else {
    const salt = await bcrypt.genSalt(10);
    const hash = await bcrypt.hash('4dm1n5MUP', salt);
    await new Admin({ username: 'admin@mail.unpad.ac.id', password: hash, role: 'SUPER_ADMIN' }).save();
    console.log('Admin berhasil dibuat!');
  }
  await mongoose.disconnect();
}

main().catch(console.error);
