import { readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { compile } from 'json-schema-to-typescript'

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url))
const frontendDirectory = path.resolve(scriptDirectory, '..')
const schemaPath = path.resolve(frontendDirectory, '../shared/scene.schema.json')
const outputPath = path.resolve(frontendDirectory, 'src/types/scene.generated.ts')
const schema = JSON.parse(await readFile(schemaPath, 'utf8'))

const source = await compile(schema, 'PromptTo3DWorldScene', {
  bannerComment: '/* Generated from shared/scene.schema.json. Do not edit by hand. */',
  format: true,
  style: { singleQuote: true, semi: false },
  unknownAny: false,
})

await writeFile(outputPath, source, 'utf8')

