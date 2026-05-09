#!/bin/bash
set -e
cd "$(dirname "$0")/../frontend"
npm install
npm run dev
