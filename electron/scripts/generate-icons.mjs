#!/usr/bin/env node
// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Icon generator — creates placeholder PNG and ICO files for the Electron build.
 *
 * This produces a simple 256x256 PNG and a basic ICO file from raw pixel data.
 * Replace with a proper designed icon before the v1 release.
 *
 * Usage: node scripts/generate-icons.mjs
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import zlib from "node:zlib";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const buildDir = path.resolve(__dirname, "..", "build");

// ---------------------------------------------------------------------------
// Minimal PNG generator (no external dependencies)
// ---------------------------------------------------------------------------

/**
 * Create a raw PNG file from RGBA pixel data.
 * This is a minimal implementation that produces valid PNG files.
 */
function createPNG(width, height, rgbaData) {
  // PNG signature
  const signature = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);

  // IHDR chunk
  const ihdrData = Buffer.alloc(13);
  ihdrData.writeUInt32BE(width, 0);
  ihdrData.writeUInt32BE(height, 4);
  ihdrData[8] = 8; // bit depth
  ihdrData[9] = 6; // color type: RGBA
  ihdrData[10] = 0; // compression
  ihdrData[11] = 0; // filter
  ihdrData[12] = 0; // interlace
  const ihdr = createChunk("IHDR", ihdrData);

  // IDAT chunk — raw pixel data with filter bytes
  const rawData = Buffer.alloc(height * (1 + width * 4));
  for (let y = 0; y < height; y++) {
    rawData[y * (1 + width * 4)] = 0; // filter: None
    for (let x = 0; x < width; x++) {
      const srcIdx = (y * width + x) * 4;
      const dstIdx = y * (1 + width * 4) + 1 + x * 4;
      rawData[dstIdx] = rgbaData[srcIdx]; // R
      rawData[dstIdx + 1] = rgbaData[srcIdx + 1]; // G
      rawData[dstIdx + 2] = rgbaData[srcIdx + 2]; // B
      rawData[dstIdx + 3] = rgbaData[srcIdx + 3]; // A
    }
  }
  const compressed = zlib.deflateSync(rawData);
  const idat = createChunk("IDAT", compressed);

  // IEND chunk
  const iend = createChunk("IEND", Buffer.alloc(0));

  return Buffer.concat([signature, ihdr, idat, iend]);
}

function createChunk(type, data) {
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length, 0);
  const typeBuffer = Buffer.from(type, "ascii");
  const crcData = Buffer.concat([typeBuffer, data]);
  const crc = crc32(crcData);
  const crcBuffer = Buffer.alloc(4);
  crcBuffer.writeUInt32BE(crc, 0);
  return Buffer.concat([length, typeBuffer, data, crcBuffer]);
}

// CRC32 lookup table
const crcTable = new Uint32Array(256);
for (let i = 0; i < 256; i++) {
  let c = i;
  for (let j = 0; j < 8; j++) {
    if (c & 1) c = 0xedb88320 ^ (c >>> 1);
    else c = c >>> 1;
  }
  crcTable[i] = c;
}

function crc32(buf) {
  let crc = 0xffffffff;
  for (let i = 0; i < buf.length; i++) {
    crc = crcTable[(crc ^ buf[i]) & 0xff] ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

// ---------------------------------------------------------------------------
// ICO file generator
// ---------------------------------------------------------------------------

/**
 * Create a basic ICO file containing one 256x256 PNG image.
 */
function createICO(pngData) {
  // ICO header: 6 bytes
  const header = Buffer.alloc(6);
  header.writeUInt16LE(0, 0); // reserved
  header.writeUInt16LE(1, 2); // type: ICO
  header.writeUInt16LE(1, 4); // count: 1 image

  // ICO directory entry: 16 bytes
  const entry = Buffer.alloc(16);
  entry[0] = 0; // width (0 = 256)
  entry[1] = 0; // height (0 = 256)
  entry[2] = 0; // color palette
  entry[3] = 0; // reserved
  entry.writeUInt16LE(1, 4); // color planes
  entry.writeUInt16LE(32, 6); // bits per pixel
  entry.writeUInt32LE(pngData.length, 8); // size of image data
  entry.writeUInt32LE(22, 12); // offset (6 header + 16 entry = 22)

  return Buffer.concat([header, entry, pngData]);
}

// ---------------------------------------------------------------------------
// Generate icon pixel data
// ---------------------------------------------------------------------------

function generateIconPixels(size) {
  const rgba = Buffer.alloc(size * size * 4);
  const center = size / 2;

  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const idx = (y * size + x) * 4;

      // Rounded rectangle background
      const cornerRadius = size * 0.18;
      const margin = size * 0.06;
      const innerX = x - margin;
      const innerY = y - margin;
      const innerW = size - 2 * margin;
      const innerH = size - 2 * margin;

      const inRect =
        innerX >= 0 &&
        innerY >= 0 &&
        innerX < innerW &&
        innerY < innerH;

      // Check corners for rounding
      const inRoundedRect = inRect && (() => {
        // Bottom-right corner
        if (innerX > innerW - cornerRadius && innerY > innerH - cornerRadius) {
          const dx = innerX - (innerW - cornerRadius);
          const dy = innerY - (innerH - cornerRadius);
          return dx * dx + dy * dy <= cornerRadius * cornerRadius;
        }
        // Bottom-left corner
        if (innerX < cornerRadius && innerY > innerH - cornerRadius) {
          const dx = innerX - cornerRadius;
          const dy = innerY - (innerH - cornerRadius);
          return dx * dx + dy * dy <= cornerRadius * cornerRadius;
        }
        // Top-right corner
        if (innerX > innerW - cornerRadius && innerY < cornerRadius) {
          const dx = innerX - (innerW - cornerRadius);
          const dy = innerY - cornerRadius;
          return dx * dx + dy * dy <= cornerRadius * cornerRadius;
        }
        // Top-left corner
        if (innerX < cornerRadius && innerY < cornerRadius) {
          const dx = innerX - cornerRadius;
          const dy = innerY - cornerRadius;
          return dx * dx + dy * dy <= cornerRadius * cornerRadius;
        }
        return true;
      })();

      if (inRoundedRect) {
        // Gradient background: dark blue (#0f172a to #1e3a5f)
        const t = y / size;
        const r = Math.round(15 + t * (30 - 15));
        const g = Math.round(23 + t * (58 - 23));
        const b = Math.round(42 + t * (95 - 42));

        // Draw book shape
        const bookCenterX = size / 2;
        const bookTop = size * 0.22;
        const bookBottom = size * 0.78;
        const bookLeft = size * 0.22;
        const bookRight = size * 0.78;

        const inBook = x >= bookLeft && x <= bookRight && y >= bookTop && y <= bookBottom;

        if (inBook) {
          const spineX = bookCenterX;
          const onLeftPage = x < spineX - 1;
          const onRightPage = x > spineX + 1;

          if (onLeftPage) {
            // Left page: brighter blue (#3b82f6)
            const pageT = (y - bookTop) / (bookBottom - bookTop);
            rgba[idx] = 59; // R
            rgba[idx + 1] = 130; // G
            rgba[idx + 2] = 246; // B
            rgba[idx + 3] = 230; // A
          } else if (onRightPage) {
            // Right page: lighter blue (#60a5fa)
            rgba[idx] = 96; // R
            rgba[idx + 1] = 165; // G
            rgba[idx + 2] = 250; // B
            rgba[idx + 3] = 190; // A
          } else {
            // Spine: dark
            rgba[idx] = 15; // R
            rgba[idx + 1] = 23; // G
            rgba[idx + 2] = 42; // B
            rgba[idx + 3] = 255; // A
          }
        } else {
          // Background
          rgba[idx] = r;
          rgba[idx + 1] = g;
          rgba[idx + 2] = b;
          rgba[idx + 3] = 255;
        }
      } else {
        // Outside rounded rect — transparent
        rgba[idx] = 0;
        rgba[idx + 1] = 0;
        rgba[idx + 2] = 0;
        rgba[idx + 3] = 0;
      }
    }
  }

  return rgba;
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

function main() {
  fs.mkdirSync(buildDir, { recursive: true });

  // Generate 256x256 PNG for ICO source
  console.log("[generate-icons] Generating 256x256 PNG...");
  const pixels256 = generateIconPixels(256);
  const png256 = createPNG(256, 256, pixels256);
  fs.writeFileSync(path.join(buildDir, "icon-256.png"), png256);
  console.log(`[generate-icons] Wrote icon-256.png (${png256.length} bytes)`);

  // Generate 512x512 PNG for Linux and macOS ICNS source
  console.log("[generate-icons] Generating 512x512 PNG...");
  const pixels512 = generateIconPixels(512);
  const png512 = createPNG(512, 512, pixels512);
  fs.writeFileSync(path.join(buildDir, "icon.png"), png512);
  console.log(`[generate-icons] Wrote icon.png (${png512.length} bytes)`);

  // Generate ICO from 256x256 PNG
  console.log("[generate-icons] Generating ICO...");
  const ico = createICO(png256);
  fs.writeFileSync(path.join(buildDir, "icon.ico"), ico);
  console.log(`[generate-icons] Wrote icon.ico (${ico.length} bytes)`);

  // Generate macOS .icns file.
  // The ICNS format requires an 'icns' container with icon data entries.
  // Each entry has a 4-byte type, 4-byte length, and the image data.
  // We include multiple sizes for best compatibility: 16, 32, 128, 256, 512.
  console.log("[generate-icons] Generating ICNS...");
  const sizes = [16, 32, 128, 256, 512];
  const icnsEntries = [];
  for (const size of sizes) {
    const pixels = generateIconPixels(size);
    const png = createPNG(size, size, pixels);
    // ICNS type codes: is32=16x16, is32m=16x16@2x=32px, ih32=32x32, ih32m=32x32@2x=128px,
    // ic32=128x128 (?), ic32m=128x128@2x=256px, icp4=256x256 (?), icp5=32x32,
    // icp6=64x64, ic07=128x128, ic08=256x256, ic09=512x512, ic10=512x512@2x=1024px
    // Modern ICNS uses PNG format for larger sizes.
    // Type codes for PNG-based icons:
    //   icp4 = 16x16, icp5 = 32x32, icp6 = 64x64,
    //   ic07 = 128x128, ic08 = 256x256, ic09 = 512x512, ic10 = 1024x1024 (retina 512)
    const typeMap = { 16: "icp4", 32: "icp5", 128: "ic07", 256: "ic08", 512: "ic09" };
    const type = typeMap[size];
    if (type) {
      icnsEntries.push({ type, data: png });
    }
  }
  const icns = createICNS(icnsEntries);
  fs.writeFileSync(path.join(buildDir, "icon.icns"), icns);
  console.log(`[generate-icons] Wrote icon.icns (${icns.length} bytes)`);

  // Generate macOS tray template icon (monochrome, for dark/light mode adaptation).
  // Template icons should be 22x22 @1x (44x44 @2x) and purely black with alpha.
  // macOS automatically adapts template icons to the menu bar appearance.
  console.log("[generate-icons] Generating macOS tray template icon...");
  const trayPixels = generateTrayIconPixels(44); // @2x size for retina
  const trayPng = createPNG(44, 44, trayPixels);
  fs.writeFileSync(path.join(buildDir, "tray-icon-template.png"), trayPng);
  console.log(`[generate-icons] Wrote tray-icon-template.png (${trayPng.length} bytes)`);

  // Also generate a 22x22 @1x version.
  const trayPixels1x = generateTrayIconPixels(22);
  const trayPng1x = createPNG(22, 22, trayPixels1x);
  fs.writeFileSync(path.join(buildDir, "tray-icon-template@1x.png"), trayPng1x);
  console.log(`[generate-icons] Wrote tray-icon-template@1x.png (${trayPng1x.length} bytes)`);

  console.log("[generate-icons] Done! Replace with a proper designed icon before release.");
}

// ---------------------------------------------------------------------------
// ICNS file generator (macOS)
// ---------------------------------------------------------------------------

/**
 * Create a macOS .icns file from an array of PNG icon entries.
 *
 * The ICNS format is a container with a 4-byte magic ('icns'), 4-byte file size,
 * followed by entries each with a 4-byte type code, 4-byte entry size, and data.
 *
 * For PNG-based icons, the data is the raw PNG bytes — macOS handles the
 * decompression and scaling natively.
 */
function createICNS(entries) {
  // Calculate total size: 8 bytes header + sum of each entry (8 bytes header + data)
  let dataSize = 8; // file header
  const entryBuffers = [];

  for (const entry of entries) {
    const typeBuffer = Buffer.from(entry.type, "ascii");
    const dataLen = entry.data.length;
    const entrySize = 8 + dataLen; // type(4) + size(4) + data
    const sizeBuffer = Buffer.alloc(4);
    sizeBuffer.writeUInt32BE(entrySize, 0);
    const entryBuf = Buffer.concat([typeBuffer, sizeBuffer, entry.data]);
    entryBuffers.push(entryBuf);
    dataSize += entrySize;
  }

  // File header: 'icns' magic + total file size
  const header = Buffer.alloc(8);
  header.write("icns", 0, "ascii");
  header.writeUInt32BE(dataSize, 4);

  return Buffer.concat([header, ...entryBuffers]);
}

// ---------------------------------------------------------------------------
// Tray icon pixel generator (macOS template icon)
// ---------------------------------------------------------------------------

/**
 * Generate pixels for a macOS tray template icon.
 *
 * Template icons are monochrome (black + alpha only). macOS automatically
 * adjusts them for light/dark mode. The icon is a simple book/reader shape
 * matching the app icon but simplified for the 16x16/22x22 tray size.
 *
 * @param {number} size - Icon size in pixels (22 for @1x, 44 for @2x)
 * @returns {Buffer} RGBA pixel data
 */
function generateTrayIconPixels(size) {
  const rgba = Buffer.alloc(size * size * 4);
  // All pixels start transparent (Buffer.alloc initializes to 0).

  // Draw a simplified book/reader shape as black with alpha.
  // The shape is scaled relative to the icon size.
  const margin = Math.max(1, Math.round(size * 0.1));
  const bookLeft = margin;
  const bookRight = size - margin;
  const bookTop = margin;
  const bookBottom = size - margin;
  const spineX = Math.round(size / 2);

  for (let y = bookTop; y < bookBottom; y++) {
    for (let x = bookLeft; x < bookRight; x++) {
      const idx = (y * size + x) * 4;

      // Left page or right page (not the spine gap).
      const isLeftPage = x < spineX - 1;
      const isRightPage = x > spineX + 1;
      const isSpine = x >= spineX - 1 && x <= spineX + 1;

      if (isLeftPage || isRightPage || isSpine) {
        // Black fill with full opacity for the book shape.
        rgba[idx] = 0;     // R (black for template)
        rgba[idx + 1] = 0;  // G
        rgba[idx + 2] = 0;  // B
        rgba[idx + 3] = 255; // A (fully opaque)
      }
      // Else: remains transparent (0,0,0,0) — the background.
    }
  }

  return rgba;
}

main();