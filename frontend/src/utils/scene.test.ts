import { describe, expect, it } from 'vitest'
import sampleScene from '@shared/examples/cyberpunk-alley.json'
import type { SceneDocument } from '@/types/scene'
import { buildCollisionBoxes, canOccupy, getSceneStats } from './scene'

const scene = sampleScene as SceneDocument

describe('scene runtime helpers', () => {
  it('reports the scene budget used by the runtime', () => {
    const stats = getSceneStats(scene)
    expect(stats.nodes).toBe(scene.nodes.length)
    expect(stats.lights).toBeGreaterThanOrEqual(2)
    expect(stats.signs).toBeGreaterThanOrEqual(1)
  })

  it('keeps the initial camera in a walkable area', () => {
    const collisions = buildCollisionBoxes(scene)
    expect(canOccupy(scene.camera.position[0], scene.camera.position[2], collisions)).toBe(true)
  })

  it('blocks movement through a solid building', () => {
    const collisions = buildCollisionBoxes(scene)
    expect(canOccupy(-6, 1, collisions)).toBe(false)
  })
})
