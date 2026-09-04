/* Generated from shared/scene.schema.json. Do not edit by hand. */

export type Id = string
export type Color = string
/**
 * @minItems 3
 * @maxItems 3
 */
export type Vector3 = [number, number, number]
/**
 * @minItems 3
 * @maxItems 3
 */
export type Rotation3 = [number, number, number]
/**
 * @minItems 3
 * @maxItems 3
 */
export type Scale3 = [number, number, number]

/**
 * The trusted, declarative scene contract shared by the API and renderer.
 */
export interface PromptTo3DWorldScene {
  schemaVersion: '1.0.0'
  id: Id
  title: string
  seed: number
  units: 'meters'
  environment: Environment
  camera: Camera
  /**
   * @minItems 8
   * @maxItems 250
   */
  nodes: [
    PrimitiveNode | TextNode | LightNode | GroupNode,
    PrimitiveNode | TextNode | LightNode | GroupNode,
    PrimitiveNode | TextNode | LightNode | GroupNode,
    PrimitiveNode | TextNode | LightNode | GroupNode,
    PrimitiveNode | TextNode | LightNode | GroupNode,
    PrimitiveNode | TextNode | LightNode | GroupNode,
    PrimitiveNode | TextNode | LightNode | GroupNode,
    PrimitiveNode | TextNode | LightNode | GroupNode,
    ...(PrimitiveNode | TextNode | LightNode | GroupNode)[]
  ]
  metadata: Metadata
  extensions: {}
}
export interface Environment {
  sky: 'night' | 'day' | 'sunrise' | 'sunset' | 'overcast' | 'indoor' | 'custom'
  background: Color
  fog: {
    type: 'none' | 'linear' | 'exponential'
    color: Color
    density: number
    near: number
    far: number
  }
  ambientLight: {
    color: Color
    intensity: number
  }
  toneMapping: 'acesFilmic' | 'linear' | 'reinhard' | 'cineon'
  exposure: number
  postprocessing: {
    bloom: {
      enabled: boolean
      intensity: number
      threshold: number
    }
  }
}
export interface Camera {
  mode: 'firstPerson'
  position: Vector3
  lookAt: Vector3
  fov: number
  near: number
  far: number
  movement: {
    speed: number
    sprintMultiplier: number
    eyeHeight: number
    baseElevation?: number
  }
}
export interface PrimitiveNode {
  id: Id
  kind: 'primitive'
  subtype: 'box' | 'plane' | 'sphere' | 'cylinder'
  parentId: Id | null
  transform: Transform
  material: Material
  semantics: Semantics
  collision: Collision
  provenance?: Provenance
}
export interface Transform {
  position: Vector3
  rotation: Rotation3
  scale: Scale3
}
export interface Material {
  type: 'standard'
  color: Color
  roughness: number
  metalness: number
  opacity: number
  transparent: boolean
  emissive: Color | null
  emissiveIntensity: number
}
export interface Semantics {
  category: string
  /**
   * @maxItems 8
   */
  tags:
    | []
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string]
    | [string, string, string, string, string, string]
    | [string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string]
}
export interface Collision {
  mode: 'none' | 'ground' | 'solid'
}
export interface Provenance {
  entityId: Id | null
  origin: 'prompt' | 'structural' | 'style' | 'system' | 'legacy'
  capabilityId: string
  reason: string
  confidence: number
  userRemovable: boolean
}
export interface TextNode {
  id: Id
  kind: 'text'
  subtype: 'label'
  parentId: Id | null
  transform: Transform
  text: {
    value: string
    fontSize: number
    align: 'left' | 'center' | 'right'
  }
  material: Material
  semantics: Semantics
  provenance?: Provenance
}
export interface LightNode {
  id: Id
  kind: 'light'
  subtype: 'ambient' | 'directional' | 'point' | 'spot'
  parentId: Id | null
  transform: Transform
  light: {
    color: Color
    intensity: number
    range: number
    decay: number
    castShadow: boolean
  }
  semantics: Semantics
  provenance?: Provenance
}
export interface GroupNode {
  id: Id
  kind: 'group'
  subtype: 'group'
  parentId: Id | null
  transform: Transform
  semantics: Semantics
  provenance?: Provenance
}
export interface Metadata {
  generator: string
  promptLanguage: 'zh' | 'en' | 'mixed' | 'unknown'
}
