/**
 * Deterministic generator for sdk/generated/catalogue.ts.
 *
 * Node standard library only. Refuses a live server, a production endpoint,
 * or a source pin that does not match protocol_contract.json bytes.
 */
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(fileURLToPath(new URL("../..", import.meta.url)));
const OPENAPI_PATH = "docs/contracts/openapi/kix-protocol.contract-only.openapi.json";
const SOURCE_PATH = "reference/v0.3-rc1/protocol_contract.json";
const FSM_PATH = "docs/contracts/openapi/fsm-command-contract.json";
const CATALOGUE_PATH = "sdk/generated/catalogue.ts";
const PIN_PATH = "sdk/sdk-pin.json";

function argument(name, fallback) {
  const index = process.argv.indexOf(name);
  if (index === -1) {
    return fallback;
  }
  const value = process.argv[index + 1];
  if (!value || value.startsWith("--")) {
    throw new Error(`missing value for ${name}`);
  }
  return value;
}

function fail(message) {
  console.error(`generate_client: ${message}`);
  process.exit(1);
}

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function gitBlobId(bytes) {
  const header = Buffer.from(`blob ${bytes.length}\0`, "ascii");
  return createHash("sha1").update(header).update(bytes).digest("hex");
}

function walk(value, visit) {
  if (Array.isArray(value)) {
    for (const item of value) {
      walk(item, visit);
    }
    return;
  }
  if (value && typeof value === "object") {
    for (const [key, child] of Object.entries(value)) {
      visit(key, child);
      walk(child, visit);
    }
  }
}

function emitJson(value, indent) {
  const json = JSON.stringify(value, null, 2);
  const pad = " ".repeat(indent);
  return json
    .split("\n")
    .map((line, index) => (index === 0 ? line : pad + line))
    .join("\n");
}

function emitStringList(values, indent) {
  const pad = " ".repeat(indent);
  return values.map((value) => `${pad}${JSON.stringify(value)},`).join("\n");
}

function sortedObject(entries) {
  return Object.fromEntries(entries);
}

function main() {
  const openapiFile = resolve(argument("--openapi", resolve(ROOT, OPENAPI_PATH)));
  const sourceFile = resolve(argument("--source", resolve(ROOT, SOURCE_PATH)));
  const catalogueFile = resolve(argument("--out", resolve(ROOT, CATALOGUE_PATH)));
  const pinFile = resolve(argument("--pin", resolve(ROOT, PIN_PATH)));

  const openapiBytes = readFileSync(openapiFile);
  const sourceBytes = readFileSync(sourceFile);
  let document;
  let contract;
  try {
    document = JSON.parse(openapiBytes.toString("utf8"));
    contract = JSON.parse(sourceBytes.toString("utf8"));
  } catch (error) {
    fail(`invalid JSON: ${error.message}`);
  }

  const sourceSha = sha256(sourceBytes);
  const sourceBlob = gitBlobId(sourceBytes);
  const openapiSha = sha256(openapiBytes);
  const openapiBlob = gitBlobId(openapiBytes);
  const pinned = document["x-kix-source"] ?? {};

  if (document.openapi !== "3.1.0") {
    fail("openapi version must be 3.1.0");
  }
  if (document["x-kix-contract-status"] !== "contract-only") {
    fail("x-kix-contract-status must be contract-only");
  }
  if (document["x-kix-live-http-server"] !== false) {
    fail("x-kix-live-http-server must be false");
  }
  if (document["x-kix-production-endpoint"] !== false) {
    fail("x-kix-production-endpoint must be false");
  }
  if (!Array.isArray(document["x-kix-omitted-commands"]) || document["x-kix-omitted-commands"].length !== 0) {
    fail("omitted command list must stay empty");
  }
  if (pinned.path !== SOURCE_PATH) {
    fail("source path drift");
  }
  if (pinned.sha256 !== sourceSha || pinned.gitBlob !== sourceBlob) {
    fail("source pin does not match protocol_contract.json bytes");
  }
  if (pinned.domain !== contract.domain) {
    fail("domain drift");
  }
  if (pinned.unknownFields !== "REJECT" || contract.unknownFields !== "REJECT") {
    fail("unknownFields must be REJECT");
  }
  if (pinned.sourceAuthentication !== "FIXTURE_ONLY") {
    fail("sourceAuthentication must be FIXTURE_ONLY");
  }
  const fsmPin = pinned.fsmSource ?? {};
  if (fsmPin.path !== FSM_PATH) {
    fail("fsm source path drift");
  }
  const fsmBytes = readFileSync(resolve(ROOT, FSM_PATH));
  const fsmSha = sha256(fsmBytes);
  const fsmBlob = gitBlobId(fsmBytes);
  if (fsmPin.sha256 !== fsmSha || fsmPin.gitBlob !== fsmBlob) {
    fail("fsm source pin does not match fsm-command-contract.json bytes");
  }
  let fsm;
  try {
    fsm = JSON.parse(fsmBytes.toString("utf8"));
  } catch (error) {
    fail(`invalid FSM JSON: ${error.message}`);
  }
  if (fsmPin.domain !== fsm.domain || fsm.unknownFields !== "REJECT" || fsm.sourceAuthentication !== "FIXTURE_ONLY") {
    fail("fsm source label drift");
  }
  if (pinned.coreCommandCount !== 40 || fsmPin.commandCount !== 44 || pinned.commandCount !== 84) {
    fail("command count drift");
  }

  walk(document, (key, child) => {
    if (key === "servers" || key === "security" || key === "securitySchemes" || key === "url") {
      fail(`forbidden transport or auth field: ${key}`);
    }
    if (typeof child === "string") {
      const lower = child.toLowerCase();
      if (lower.includes("http://") || lower.includes("https://") || lower.includes("localhost")) {
        fail(`forbidden endpoint string near key ${key}`);
      }
    }
  });

  const schemas = document.components?.schemas ?? {};
  const names = Object.keys(schemas).filter((name) => name !== "LocalCallEnvelope");
  if (names.length !== pinned.commandCount) {
    fail("commandCount drift");
  }
  if (Object.keys(schemas).length !== names.length + 1) {
    fail("schema set drift");
  }
  const actionMap = document["x-kix-action-body-map"] ?? {};
  if (Object.keys(actionMap).join("\n") !== names.join("\n")) {
    fail("action map drift");
  }
  const envelope = schemas.LocalCallEnvelope ?? {};
  const required = envelope.required ?? [];
  if (required.join("\n") !== ["operationId", "actor", "action", "body"].join("\n")) {
    fail("envelope parameter list drift");
  }
  const actionEnum = envelope.properties?.action?.enum ?? [];
  if (actionEnum.join("\n") !== names.join("\n")) {
    fail("action enum drift");
  }
  for (const name of names) {
    const schema = schemas[name];
    if (!schema || schema.additionalProperties !== false || schema.type !== "object") {
      fail(`additionalProperties is not false: ${name}`);
    }
    if (actionMap[name] !== `#/components/schemas/${name}`) {
      fail(`action map ref drift: ${name}`);
    }
  }

  const fsmNames = Object.keys(fsm.commands);
  if (names.filter((name) => Object.hasOwn(fsm.commands, name)).join("\n") !== fsmNames.join("\n")) {
    fail("fsm command set drift");
  }
  const pinObject = {
    commandCount: names.length,
    coreCommandCount: pinned.coreCommandCount,
    domain: pinned.domain,
    fsmCommandCount: fsmPin.commandCount,
    fsmSource: {
      domain: fsmPin.domain,
      gitBlob: fsmBlob,
      path: FSM_PATH,
      sha256: fsmSha,
    },
    generatedCatalogue: CATALOGUE_PATH,
    generator: "sdk/generate/generate_client.mjs",
    openapi: {
      gitBlob: openapiBlob,
      path: OPENAPI_PATH,
      sha256: openapiSha,
    },
    source: {
      domain: pinned.domain,
      gitBlob: sourceBlob,
      path: SOURCE_PATH,
      sha256: sourceSha,
    },
    sourceAuthentication: pinned.sourceAuthentication,
    unknownFields: pinned.unknownFields,
  };

  const commandLines = emitStringList(names, 2);
  const actionLines = names
    .map((name) => `  ${JSON.stringify(name)}: ${JSON.stringify(actionMap[name])},`)
    .join("\n");
  const schemaLines = names
    .map((name) => `  ${JSON.stringify(name)}: ${emitJson(schemas[name], 2)},`)
    .join("\n");
  const machineLines = fsmNames
    .map((name) => `  ${JSON.stringify(name)}: ${JSON.stringify(fsm.commands[name].machine)},`)
    .join("\n");
  const catalogue = `// @generated by sdk/generate/generate_client.mjs
// Do not edit. scripts/check_sdk_client.py checks byte-identical regeneration.
//
// Non-production contract-only catalogue.
// No base URL. Actor is not an authentication result. No delivery inference.

export const OPENAPI_PIN = ${emitJson(
    sortedObject([
      ["commandCount", names.length],
      ["contractStatus", "contract-only"],
      ["coreCommandCount", pinned.coreCommandCount],
      ["domain", pinned.domain],
      ["fsmCommandCount", fsmPin.commandCount],
      ["fsmSourceGitBlob", fsmBlob],
      ["fsmSourcePath", FSM_PATH],
      ["fsmSourceSha256", fsmSha],
      ["gitBlob", openapiBlob],
      ["liveHttpServer", false],
      ["openapiPath", OPENAPI_PATH],
      ["productionEndpoint", false],
      ["sha256", openapiSha],
      ["sourceAuthentication", "FIXTURE_ONLY"],
      ["sourceGitBlob", sourceBlob],
      ["sourcePath", SOURCE_PATH],
      ["sourceSha256", sourceSha],
      ["unknownFields", "REJECT"],
    ]),
    0,
  )} as const;

export const ENVELOPE_REQUIRED = ["operationId", "actor", "action", "body"] as const;

export const COMMANDS = [
${commandLines}
] as const;

export type CommandName = (typeof COMMANDS)[number];

export const ACTION_BODY_MAP = {
${actionLines}
} as const;

export const COMMAND_SCHEMAS = {
${schemaLines}
} as const;

export const FSM_COMMAND_MACHINES = {
${machineLines}
} as const;
`;

  mkdirSync(dirname(catalogueFile), { recursive: true });
  mkdirSync(dirname(pinFile), { recursive: true });
  writeFileSync(catalogueFile, catalogue, "utf8");
  writeFileSync(pinFile, `${JSON.stringify(pinObject, null, 2)}\n`, "utf8");
}

main();
