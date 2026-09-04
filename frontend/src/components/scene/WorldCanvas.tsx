import { AdaptiveDpr, OrbitControls } from '@react-three/drei'
import { Canvas, useThree } from '@react-three/fiber'
import { Bloom, EffectComposer } from '@react-three/postprocessing'
import { useEffect, useRef } from 'react'
import {
  ACESFilmicToneMapping,
  CineonToneMapping,
  Color,
  Fog,
  FogExp2,
  LinearToneMapping,
  PerspectiveCamera,
  ReinhardToneMapping,
} from 'three'
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib'
import type { SceneDocument } from '@/types/scene'
import { FirstPersonController } from './FirstPersonController'
import { SceneGraph } from './SceneGraph'

interface WorldCanvasProps {
  scene: SceneDocument
  resetRequest: number
  onLockedChange: (locked: boolean) => void
  onRuntimeError: (message: string | null) => void
  onNodeSelect?: (nodeId: string) => void
}

function SceneEnvironment({ scene, onRuntimeError }: Pick<WorldCanvasProps, 'scene' | 'onRuntimeError'>) {
  const world = useThree((state) => state.scene)
  const renderer = useThree((state) => state.gl)
  const camera = useThree((state) => state.camera)

  useEffect(() => {
    world.background = new Color(scene.environment.background)
    const fog = scene.environment.fog
    world.fog =
      fog.type === 'exponential'
        ? new FogExp2(fog.color, fog.density)
        : fog.type === 'linear'
          ? new Fog(fog.color, fog.near, fog.far)
          : null

    const mappings = {
      acesFilmic: ACESFilmicToneMapping,
      linear: LinearToneMapping,
      reinhard: ReinhardToneMapping,
      cineon: CineonToneMapping,
    }
    renderer.toneMapping = mappings[scene.environment.toneMapping]
    renderer.toneMappingExposure = scene.environment.exposure
    if (camera instanceof PerspectiveCamera) {
      camera.near = scene.camera.near
      camera.far = scene.camera.far
      camera.fov = scene.camera.fov
      camera.updateProjectionMatrix()
    }
    renderer.shadowMap.autoUpdate = true
    onRuntimeError(null)
  }, [camera, onRuntimeError, renderer, scene, world])

  useEffect(() => {
    const canvas = renderer.domElement
    const onLost = (event: Event) => {
      event.preventDefault()
      onRuntimeError('WebGL 上下文已丢失，请刷新页面恢复场景。')
    }
    const onRestored = () => onRuntimeError(null)
    canvas.addEventListener('webglcontextlost', onLost)
    canvas.addEventListener('webglcontextrestored', onRestored)
    return () => {
      canvas.removeEventListener('webglcontextlost', onLost)
      canvas.removeEventListener('webglcontextrestored', onRestored)
    }
  }, [onRuntimeError, renderer])

  return null
}

function OrbitSceneController({
  scene,
  resetRequest,
  onLockedChange,
}: Pick<WorldCanvasProps, 'scene' | 'resetRequest' | 'onLockedChange'>) {
  const camera = useThree((state) => state.camera)
  const controls = useRef<OrbitControlsImpl | null>(null)

  useEffect(() => {
    onLockedChange(false)
    camera.position.set(...scene.camera.position)
    camera.lookAt(...scene.camera.lookAt)
    controls.current?.target.set(...scene.camera.lookAt)
    controls.current?.update()
    camera.updateProjectionMatrix()
  }, [camera, onLockedChange, resetRequest, scene.camera.lookAt, scene.camera.position, scene.id])

  return (
    <OrbitControls
      ref={controls}
      makeDefault
      target={scene.camera.lookAt}
      enableDamping
      dampingFactor={0.075}
      enablePan={scene.camera.mode !== 'panorama'}
      enableZoom
      minDistance={scene.camera.mode === 'panorama' ? 0.5 : 4}
      maxDistance={scene.camera.mode === 'panorama' ? 30 : 180}
      rotateSpeed={0.55}
      zoomSpeed={0.72}
    />
  )
}

export function WorldCanvas({ scene, resetRequest, onLockedChange, onRuntimeError, onNodeSelect }: WorldCanvasProps) {
  const bloom = scene.environment.postprocessing.bloom
  return (
    <Canvas
      className="world-canvas"
      shadows
      dpr={[1, 1.5]}
      camera={{
        position: scene.camera.position,
        fov: scene.camera.fov,
        near: scene.camera.near,
        far: scene.camera.far,
      }}
      gl={{ antialias: true, powerPreference: 'high-performance', alpha: false }}
      fallback={<div className="canvas-fallback">当前浏览器无法启动 WebGL。</div>}
    >
      <SceneEnvironment scene={scene} onRuntimeError={onRuntimeError} />
      <ambientLight
        color={scene.environment.ambientLight.color}
        intensity={scene.environment.ambientLight.intensity}
      />
      <SceneGraph scene={scene} onNodeSelect={onNodeSelect} />
      {scene.camera.mode === 'firstPerson' ? (
        <FirstPersonController
          scene={scene}
          resetRequest={resetRequest}
          onLockedChange={onLockedChange}
        />
      ) : (
        <OrbitSceneController
          scene={scene}
          resetRequest={resetRequest}
          onLockedChange={onLockedChange}
        />
      )}
      <AdaptiveDpr />
      {bloom.enabled ? (
        <EffectComposer multisampling={0} enableNormalPass={false}>
          <Bloom
            mipmapBlur
            intensity={bloom.intensity}
            luminanceThreshold={bloom.threshold}
            luminanceSmoothing={0.2}
          />
        </EffectComposer>
      ) : null}
    </Canvas>
  )
}
