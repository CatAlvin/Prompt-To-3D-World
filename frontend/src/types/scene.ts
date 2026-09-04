import type { PromptTo3DWorldScene } from './scene.generated'

export type SceneDocumentV1 = PromptTo3DWorldScene
export type SceneMaterial = Extract<SceneDocumentV1['nodes'][number], { kind: 'primitive' }>['material']
export type Transform = SceneDocumentV1['nodes'][number]['transform']
export type Semantics = SceneDocumentV1['nodes'][number]['semantics']

interface V2NodeBase {
  id: string
  parentId: string | null
  transform: Transform
  semantics: Semantics
}

export interface NodeProvenance {
  entityId: string | null
  origin: 'prompt' | 'structural' | 'style' | 'system' | 'legacy'
  capabilityId: string
  reason: string
  confidence: number
  userRemovable: boolean
}

export interface EffectNode {
  id: string
  kind: 'effect'
  subtype: 'starfield' | 'star' | 'pulsar' | 'black_hole' | 'planet' | 'crater' | 'cloud_field'
  parentId: string | null
  transform: Transform
  parameters: {
    count: number
    color: string
    secondaryColor: string
    size: number
    intensity: number
    radius: number
    spread: number
    rotationSpeed: number
  }
  semantics: Semantics
  provenance: NodeProvenance
}

export interface ProceduralNode extends V2NodeBase {
  kind: 'procedural'
  subtype: 'building_row' | 'shopfront_row' | 'tree_cluster' | 'rock_cluster' | 'interior_shell' | 'prop_scatter'
  generator: string
  parameters: { count: number; spacing: number; spread: number; height: number }
  fallback: 'boxes' | 'cylinders' | 'spheres'
}

export interface AssetNode extends V2NodeBase {
  kind: 'asset'
  subtype: 'catalog_asset'
  assetRef: string
  variant: string
  lod: number
  collision: { mode: 'none' | 'ground' | 'solid' }
  fallback: 'box' | 'sphere' | 'cylinder'
}

export interface PrefabNode extends V2NodeBase {
  kind: 'prefab'
  subtype: 'registered_prefab'
  prefabRef: 'prefab_shopfront_v1' | 'prefab_shrine_gate_v1' | 'prefab_cozy_window_v1' | 'prefab_lunar_module_v1'
}

export interface InstancesNode extends V2NodeBase {
  kind: 'instances'
  subtype: 'primitive_instances'
  source: { primitive: 'box' | 'sphere' | 'cylinder'; material: SceneMaterial }
  instances: Transform[]
}

export interface DecalNode extends V2NodeBase {
  kind: 'decal'
  subtype: 'puddle' | 'marking' | 'poster'
  material: SceneMaterial
}

export type V1SceneNode = SceneDocumentV1['nodes'][number]
export type SceneNode = V1SceneNode | ProceduralNode | AssetNode | PrefabNode | InstancesNode | DecalNode | EffectNode

export interface SceneDocumentV2 extends Omit<SceneDocumentV1, 'schemaVersion' | 'nodes' | 'extensions'> {
  schemaVersion: '2.0.0'
  nodes: SceneNode[]
  pipeline: {
    versionKind: 'draft' | 'final'
    planVersion: '1.0.0'
    compilerVersion: 'procedural-2.0.0' | 'procedural-2.0.1'
    styleKit: 'cyberpunk_tokyo_v1' | 'cozy_lowpoly_v1' | 'misty_nature_v1' | 'lunar_research_v1'
    quality: 'draft' | 'balanced' | 'quality'
    archetype: 'urban_alley' | 'cozy_room' | 'misty_nature' | 'desert_outpost' | 'historic_town' | 'lunar_station'
    requestFingerprint: string
  }
  extensions: { weather?: 'clear' | 'rain' | 'mist' | 'dust'; wetness?: number }
}

export interface SceneDocumentV3 extends Omit<SceneDocumentV1, 'schemaVersion' | 'camera' | 'nodes' | 'extensions'> {
  schemaVersion: '3.0.0'
  camera: Omit<SceneDocumentV1['camera'], 'mode' | 'far'> & {
    mode: 'firstPerson' | 'orbit' | 'fly' | 'panorama'
    far: number
  }
  nodes: SceneNode[]
  pipeline: {
    versionKind: 'draft' | 'final'
    intentVersion: '2.0.0'
    compilerVersion: 'visual-recipes-3.0.0'
    styleKit: 'cyberpunk_tokyo_v1' | 'cozy_lowpoly_v1' | 'misty_nature_v1' | 'lunar_research_v1'
    quality: 'draft' | 'balanced' | 'quality'
    sceneMode: 'walkable' | 'interior' | 'orbital' | 'flythrough' | 'diorama' | 'panorama'
    requestFingerprint: string
    capabilityVersions: Record<string, string>
  }
  semanticReport: {
    status: 'pending' | 'passed' | 'failed'
    requiredCoverage: number
    relationSatisfaction: number
    forbiddenViolations: number
    unrelatedRatio: number
    heroVisible: boolean
    coveredEntityIds: string[]
    missingEntityIds: string[]
  }
  extensions: { weather: 'clear' | 'rain' | 'mist' | 'dust'; wetness: number }
}

export type SceneDocument = SceneDocumentV1 | SceneDocumentV2 | SceneDocumentV3
export type PrimitiveNode = Extract<SceneNode, { kind: 'primitive' }>
export type TextNode = Extract<SceneNode, { kind: 'text' }>
export type LightNode = Extract<SceneNode, { kind: 'light' }>
export type GroupNode = Extract<SceneNode, { kind: 'group' }>

export function isSceneV2(scene: SceneDocument): scene is SceneDocumentV2 {
  return scene.schemaVersion === '2.0.0'
}

export function isSceneV3(scene: SceneDocument): scene is SceneDocumentV3 {
  return scene.schemaVersion === '3.0.0'
}
