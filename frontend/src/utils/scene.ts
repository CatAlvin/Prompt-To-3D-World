import type { PrimitiveNode, SceneDocument } from '@/types/scene'

export interface SceneStats {
  nodes: number
  primitives: number
  lights: number
  signs: number
  collisionSolids: number
}

export interface CollisionBox {
  id: string
  minX: number
  maxX: number
  minZ: number
  maxZ: number
}

export function getSceneStats(scene: SceneDocument): SceneStats {
  return scene.nodes.reduce<SceneStats>(
    (stats, node) => {
      stats.nodes += 1
      if (node.kind === 'primitive') {
        stats.primitives += 1
        if (node.collision.mode === 'solid') stats.collisionSolids += 1
      }
      if (node.kind === 'light') stats.lights += 1
      if (node.kind === 'text') stats.signs += 1
      if (node.kind === 'instances') stats.primitives += node.instances.length
      if (node.kind === 'asset' || node.kind === 'prefab' || node.kind === 'procedural' || node.kind === 'decal') {
        stats.primitives += 1
      }
      return stats
    },
    { nodes: 0, primitives: 0, lights: 0, signs: 0, collisionSolids: 0 },
  )
}

export function buildCollisionBoxes(scene: SceneDocument): CollisionBox[] {
  return scene.nodes
    .filter(
      (node): node is PrimitiveNode =>
        node.kind === 'primitive' &&
        node.collision.mode === 'solid' &&
        node.parentId === null,
    )
    .map((node) => {
      const [x, , z] = node.transform.position
      const [scaleX, , scaleZ] = node.transform.scale
      return {
        id: node.id,
        minX: x - scaleX / 2,
        maxX: x + scaleX / 2,
        minZ: z - scaleZ / 2,
        maxZ: z + scaleZ / 2,
      }
    })
}

export function canOccupy(
  x: number,
  z: number,
  collisions: CollisionBox[],
  radius = 0.28,
): boolean {
  return !collisions.some(
    (box) =>
      x + radius > box.minX &&
      x - radius < box.maxX &&
      z + radius > box.minZ &&
      z - radius < box.maxZ,
  )
}
