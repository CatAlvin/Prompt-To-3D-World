import { PointerLockControls } from '@react-three/drei'
import { useFrame, useThree } from '@react-three/fiber'
import { useEffect, useMemo, useRef } from 'react'
import { Vector3 } from 'three'
import type { PointerLockControls as PointerLockControlsImpl } from 'three-stdlib'
import type { SceneDocument } from '@/types/scene'
import { buildCollisionBoxes, canOccupy } from '@/utils/scene'

interface FirstPersonControllerProps {
  scene: SceneDocument
  resetRequest: number
  onLockedChange: (locked: boolean) => void
}

const forward = new Vector3()
const right = new Vector3()
const movement = new Vector3()

export function FirstPersonController({
  scene,
  resetRequest,
  onLockedChange,
}: FirstPersonControllerProps) {
  const camera = useThree((state) => state.camera)
  const controls = useRef<PointerLockControlsImpl | null>(null)
  const locked = useRef(false)
  const keys = useRef(new Set<string>())
  const collisions = useMemo(() => buildCollisionBoxes(scene), [scene])

  const resetCamera = () => {
    camera.position.set(...scene.camera.position)
    camera.lookAt(...scene.camera.lookAt)
    camera.updateProjectionMatrix()
  }

  useEffect(() => {
    resetCamera()
    // Camera setup is intentionally keyed by scene identity.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scene.id, resetRequest])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!locked.current) return
      if (['KeyW', 'KeyA', 'KeyS', 'KeyD', 'ShiftLeft', 'ShiftRight'].includes(event.code)) {
        event.preventDefault()
        keys.current.add(event.code)
      }
    }
    const onKeyUp = (event: KeyboardEvent) => keys.current.delete(event.code)
    const clearKeys = () => keys.current.clear()
    window.addEventListener('keydown', onKeyDown)
    window.addEventListener('keyup', onKeyUp)
    window.addEventListener('blur', clearKeys)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      window.removeEventListener('keyup', onKeyUp)
      window.removeEventListener('blur', clearKeys)
    }
  }, [])

  useFrame((_, rawDelta) => {
    if (!locked.current) return
    const delta = Math.min(rawDelta, 0.05)
    camera.getWorldDirection(forward)
    forward.y = 0
    forward.normalize()
    right.crossVectors(forward, camera.up).normalize()

    movement.set(0, 0, 0)
    if (keys.current.has('KeyW')) movement.add(forward)
    if (keys.current.has('KeyS')) movement.sub(forward)
    if (keys.current.has('KeyD')) movement.add(right)
    if (keys.current.has('KeyA')) movement.sub(right)
    if (movement.lengthSq() === 0) return

    const sprinting = keys.current.has('ShiftLeft') || keys.current.has('ShiftRight')
    const speed = scene.camera.movement.speed * (sprinting ? scene.camera.movement.sprintMultiplier : 1)
    movement.normalize().multiplyScalar(speed * delta)

    const nextX = camera.position.x + movement.x
    const nextZ = camera.position.z + movement.z
    if (canOccupy(nextX, camera.position.z, collisions)) camera.position.x = nextX
    if (canOccupy(camera.position.x, nextZ, collisions)) camera.position.z = nextZ
    camera.position.y =
      scene.camera.movement.eyeHeight + (scene.camera.movement.baseElevation ?? 0)
  })

  return (
    <PointerLockControls
      ref={controls}
      selector="#enter-world"
      onLock={() => {
        locked.current = true
        onLockedChange(true)
      }}
      onUnlock={() => {
        locked.current = false
        keys.current.clear()
        onLockedChange(false)
      }}
    />
  )
}
