import {
  Component,
  type ComponentType,
  type ErrorInfo,
  type PropsWithChildren,
  useEffect,
  useMemo,
} from 'react'
import {
  AdditiveBlending,
  BackSide,
  CanvasTexture,
  DoubleSide,
  type Group,
  LinearFilter,
  SRGBColorSpace,
  type EulerTuple,
  type Vector3Tuple,
} from 'three'
import { Instance, Instances, Stars } from '@react-three/drei'
import { useFrame } from '@react-three/fiber'
import { useRef } from 'react'
import type {
  AssetNode,
  DecalNode,
  EffectNode,
  GroupNode,
  InstancesNode,
  LightNode,
  PrefabNode,
  PrimitiveNode,
  ProceduralNode,
  SceneDocument,
  SceneMaterial,
  SceneNode,
  TextNode,
} from '@/types/scene'

interface SceneGraphProps {
  scene: SceneDocument
  onNodeSelect?: (nodeId: string) => void
}

interface RegisteredNodeProps extends PropsWithChildren {
  node: SceneNode
}

interface NodeBoundaryProps extends PropsWithChildren {
  nodeId: string
}

interface NodeBoundaryState {
  failed: boolean
}

class NodeErrorBoundary extends Component<NodeBoundaryProps, NodeBoundaryState> {
  state: NodeBoundaryState = { failed: false }

  static getDerivedStateFromError(): NodeBoundaryState {
    return { failed: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.warn(`Scene node ${this.props.nodeId} was skipped`, error, info.componentStack)
  }

  render() {
    return this.state.failed ? null : this.props.children
  }
}

function vector(value: number[]): Vector3Tuple {
  return [value[0] ?? 0, value[1] ?? 0, value[2] ?? 0]
}

function rotation(value: number[]): EulerTuple {
  return [value[0] ?? 0, value[1] ?? 0, value[2] ?? 0, 'XYZ']
}

function StandardMaterial({ material, doubleSided = false }: { material: SceneMaterial; doubleSided?: boolean }) {
  return (
    <meshStandardMaterial
      color={material.color}
      roughness={material.roughness}
      metalness={material.metalness}
      opacity={material.opacity}
      transparent={material.transparent}
      emissive={material.emissive ?? '#050609'}
      emissiveIntensity={material.emissiveIntensity}
      side={doubleSided ? DoubleSide : undefined}
      depthWrite={material.opacity > 0.65}
    />
  )
}

function geometryFor(subtype: 'box' | 'plane' | 'sphere' | 'cylinder') {
  return {
    box: <boxGeometry args={[1, 1, 1]} />,
    plane: <planeGeometry args={[1, 1]} />,
    sphere: <sphereGeometry args={[0.5, 24, 16]} />,
    cylinder: <cylinderGeometry args={[0.5, 0.5, 1, 16]} />,
  }[subtype]
}

function PrimitiveView({ node }: { node: PrimitiveNode }) {
  const transform = node.transform
  const geometry = geometryFor(node.subtype)

  return (
    <mesh
      name={node.id}
      position={vector(transform.position)}
      rotation={rotation(transform.rotation)}
      scale={vector(transform.scale)}
      castShadow={node.collision.mode === 'solid'}
      receiveShadow={node.collision.mode !== 'none'}
      userData={{ category: node.semantics.category, tags: node.semantics.tags }}
    >
      {geometry}
      <StandardMaterial material={node.material} doubleSided={node.subtype === 'plane'} />
    </mesh>
  )
}

const fallbackMaterials: Record<string, SceneMaterial> = {
  lantern: { type: 'standard', color: '#f0b275', roughness: 0.36, metalness: 0.04, opacity: 1, transparent: false, emissive: '#e78061', emissiveIntensity: 2.8 },
  street_light: { type: 'standard', color: '#39424d', roughness: 0.72, metalness: 0.5, opacity: 1, transparent: false, emissive: null, emissiveIntensity: 0 },
  crate: { type: 'standard', color: '#77523d', roughness: 0.9, metalness: 0, opacity: 1, transparent: false, emissive: null, emissiveIntensity: 0 },
  rock: { type: 'standard', color: '#67706a', roughness: 0.98, metalness: 0, opacity: 1, transparent: false, emissive: null, emissiveIntensity: 0 },
  vegetation: { type: 'standard', color: '#496953', roughness: 0.94, metalness: 0, opacity: 1, transparent: false, emissive: null, emissiveIntensity: 0 },
  antenna: { type: 'standard', color: '#dbe3e9', roughness: 0.42, metalness: 0.7, opacity: 1, transparent: false, emissive: '#5fb9ef', emissiveIntensity: 0.18 },
}

function AssetView({ node }: { node: AssetNode }) {
  const category = node.semantics.category
  const material = fallbackMaterials[category] ?? fallbackMaterials.rock
  return (
    <mesh
      name={node.id}
      position={vector(node.transform.position)}
      rotation={rotation(node.transform.rotation)}
      scale={vector(node.transform.scale)}
      userData={{ category, assetRef: node.assetRef, catalogFallback: true }}
    >
      {geometryFor(node.fallback)}
      <StandardMaterial material={material} />
    </mesh>
  )
}

function InstancesView({ node }: { node: InstancesNode }) {
  return (
    <group
      name={node.id}
      position={vector(node.transform.position)}
      rotation={rotation(node.transform.rotation)}
      scale={vector(node.transform.scale)}
      userData={{ category: node.semantics.category, instanced: true }}
    >
      <Instances limit={node.instances.length} range={node.instances.length} castShadow receiveShadow>
        {geometryFor(node.source.primitive)}
        <StandardMaterial material={node.source.material} />
        {node.instances.map((transform, index) => (
          <Instance
            key={`${node.id}_${index}`}
            position={vector(transform.position)}
            rotation={vector(transform.rotation)}
            scale={vector(transform.scale)}
          />
        ))}
      </Instances>
    </group>
  )
}

function ProceduralView({ node }: { node: ProceduralNode }) {
  const count = Math.min(node.parameters.count, 32)
  const items = Array.from({ length: count }, (_, index) => {
    const centered = index - (count - 1) / 2
    const wobble = Math.sin(index * 12.9898 + node.id.length) * 0.45
    const position: Vector3Tuple =
      node.subtype.includes('building') || node.subtype.includes('shopfront')
        ? [0, node.parameters.height * 0.48 + wobble, centered * node.parameters.spacing]
        : [Math.sin(index * 2.34) * node.parameters.spread * 0.45, node.parameters.height * 0.42, Math.cos(index * 1.72) * node.parameters.spread * 0.44]
    const scale: Vector3Tuple =
      node.fallback === 'boxes'
        ? [1.4 + Math.abs(wobble), node.parameters.height * (0.78 + Math.abs(wobble) * 0.2), Math.max(0.7, node.parameters.spacing * 0.72)]
        : node.fallback === 'cylinders'
          ? [0.45, node.parameters.height, 0.45]
          : [1.2 + Math.abs(wobble), 0.8 + Math.abs(wobble), 1.1 + Math.abs(wobble)]
    return { position, scale }
  })
  const material = fallbackMaterials[node.semantics.category] ?? {
    ...fallbackMaterials.rock,
    color: node.fallback === 'boxes' ? '#202933' : '#405c4b',
  }
  const primitive = node.fallback === 'cylinders' ? 'cylinder' : node.fallback === 'spheres' ? 'sphere' : 'box'
  return (
    <group
      name={node.id}
      position={vector(node.transform.position)}
      rotation={rotation(node.transform.rotation)}
      scale={vector(node.transform.scale)}
      userData={{ category: node.semantics.category, generator: node.generator }}
    >
      <Instances limit={count} range={count} castShadow receiveShadow>
        {geometryFor(primitive)}
        <StandardMaterial material={material} />
        {items.map((item, index) => <Instance key={`${node.id}_generated_${index}`} position={item.position} scale={item.scale} />)}
      </Instances>
    </group>
  )
}

function ShopfrontPrefab() {
  return (
    <group>
      <mesh position={[0, 0, 0]}><boxGeometry args={[1.8, 2.4, 0.28]} /><meshStandardMaterial color="#27242a" roughness={0.78} /></mesh>
      <mesh position={[0, 0.25, 0.2]}><boxGeometry args={[1.45, 1.5, 0.12]} /><meshStandardMaterial color="#77423d" roughness={0.5} emissive="#cf5d57" emissiveIntensity={0.25} /></mesh>
      <mesh position={[0, 1.25, 0.48]} rotation={[0.18, 0, 0]}><boxGeometry args={[2.1, 0.12, 0.9]} /><meshStandardMaterial color="#8f2e4c" roughness={0.72} /></mesh>
    </group>
  )
}

function ShrineGatePrefab() {
  return (
    <group>
      <mesh position={[-1.6, 0, 0]}><boxGeometry args={[0.35, 4.2, 0.4]} /><meshStandardMaterial color="#a94b3d" roughness={0.62} /></mesh>
      <mesh position={[1.6, 0, 0]}><boxGeometry args={[0.35, 4.2, 0.4]} /><meshStandardMaterial color="#a94b3d" roughness={0.62} /></mesh>
      <mesh position={[0, 1.65, 0]}><boxGeometry args={[4.3, 0.35, 0.48]} /><meshStandardMaterial color="#bf5d46" roughness={0.58} /></mesh>
      <mesh position={[0, 2.15, 0]}><boxGeometry args={[5, 0.28, 0.42]} /><meshStandardMaterial color="#79382f" roughness={0.7} /></mesh>
    </group>
  )
}

function WindowPrefab() {
  return (
    <group>
      <mesh><boxGeometry args={[3.1, 2.2, 0.14]} /><meshStandardMaterial color="#4d382e" roughness={0.8} /></mesh>
      <mesh position={[0, 0, 0.09]}><planeGeometry args={[2.65, 1.75]} /><meshStandardMaterial color="#8eb5bb" emissive="#799ca1" emissiveIntensity={0.36} roughness={0.22} metalness={0.12} /></mesh>
      <mesh position={[0, 0, 0.18]}><boxGeometry args={[0.12, 1.82, 0.08]} /><meshStandardMaterial color="#4d382e" /></mesh>
    </group>
  )
}

function LunarModulePrefab() {
  const shell = '#e3e9ee'
  const trim = '#687686'
  const glass = '#55b9ef'
  return (
    <group>
      <mesh position={[0, 0.35, 0]} rotation={[0, 0, Math.PI / 2]} castShadow receiveShadow>
        <cylinderGeometry args={[1.15, 1.15, 5, 28]} />
        <meshStandardMaterial color={shell} roughness={0.46} metalness={0.32} />
      </mesh>
      <mesh position={[-2.5, 0.35, 0]} rotation={[0, 0, Math.PI / 2]}>
        <sphereGeometry args={[1.14, 24, 16]} />
        <meshStandardMaterial color={trim} roughness={0.58} metalness={0.42} />
      </mesh>
      <mesh position={[2.5, 0.35, 0]} rotation={[0, 0, Math.PI / 2]}>
        <sphereGeometry args={[1.14, 24, 16]} />
        <meshStandardMaterial color={trim} roughness={0.58} metalness={0.42} />
      </mesh>
      {[-1.35, 0, 1.35].map((x) => (
        <mesh key={x} position={[x, 0.55, 1.04]}>
          <boxGeometry args={[0.72, 0.5, 0.08]} />
          <meshStandardMaterial color={glass} emissive={glass} emissiveIntensity={1.45} roughness={0.18} metalness={0.2} />
        </mesh>
      ))}
      {[-1.65, 1.65].flatMap((x) => [-0.62, 0.62].map((z) => (
        <mesh key={`${x}_${z}`} position={[x, -0.92, z]}>
          <boxGeometry args={[0.22, 1.55, 0.22]} />
          <meshStandardMaterial color={trim} roughness={0.5} metalness={0.66} />
        </mesh>
      )))}
      <mesh position={[0, 1.65, 0]}>
        <cylinderGeometry args={[0.08, 0.08, 1.5, 12]} />
        <meshStandardMaterial color={trim} metalness={0.74} roughness={0.35} />
      </mesh>
      <mesh position={[0, 2.42, 0]} rotation={[0.25, 0, 0]}>
        <cylinderGeometry args={[0.62, 0.18, 0.18, 24]} />
        <meshStandardMaterial color={shell} metalness={0.52} roughness={0.4} />
      </mesh>
    </group>
  )
}

function PrefabView({ node }: { node: PrefabNode }) {
  const content =
    node.prefabRef === 'prefab_shrine_gate_v1'
      ? <ShrineGatePrefab />
      : node.prefabRef === 'prefab_cozy_window_v1'
        ? <WindowPrefab />
        : node.prefabRef === 'prefab_lunar_module_v1'
          ? <LunarModulePrefab />
          : <ShopfrontPrefab />
  return (
    <group
      name={node.id}
      position={vector(node.transform.position)}
      rotation={rotation(node.transform.rotation)}
      scale={vector(node.transform.scale)}
      userData={{ category: node.semantics.category, prefabRef: node.prefabRef }}
    >
      {content}
    </group>
  )
}

function DecalView({ node }: { node: DecalNode }) {
  return (
    <mesh
      name={node.id}
      position={vector(node.transform.position)}
      rotation={rotation(node.transform.rotation)}
      scale={vector(node.transform.scale)}
      receiveShadow
      userData={{ category: node.semantics.category, decal: node.subtype }}
    >
      <planeGeometry args={[1, 1]} />
      <StandardMaterial material={node.material} doubleSided />
    </mesh>
  )
}

function useLabelTexture(node: TextNode): CanvasTexture {
  const texture = useMemo(() => {
    const canvas = document.createElement('canvas')
    canvas.width = 1024
    canvas.height = 256
    const context = canvas.getContext('2d')
    if (!context) throw new Error('Canvas 2D is unavailable')

    const glow = node.material.emissive ?? node.material.color
    context.clearRect(0, 0, canvas.width, canvas.height)
    context.textAlign = node.text.align
    context.textBaseline = 'middle'
    context.font = '700 112px "Outfit Variable", "Microsoft YaHei", sans-serif'
    context.lineJoin = 'round'
    context.shadowColor = glow
    context.shadowBlur = 34
    context.strokeStyle = glow
    context.lineWidth = 6
    context.fillStyle = node.material.color
    const x = node.text.align === 'left' ? 44 : node.text.align === 'right' ? 980 : 512
    context.strokeText(node.text.value, x, 132, 930)
    context.fillText(node.text.value, x, 132, 930)

    const created = new CanvasTexture(canvas)
    created.colorSpace = SRGBColorSpace
    created.minFilter = LinearFilter
    created.magFilter = LinearFilter
    created.needsUpdate = true
    return created
  }, [node.material.color, node.material.emissive, node.text.align, node.text.value])

  useEffect(() => () => texture.dispose(), [texture])
  return texture
}

function TextView({ node }: { node: TextNode }) {
  const texture = useLabelTexture(node)
  const width = Math.min(8, Math.max(1.3, node.text.value.length * node.text.fontSize * 0.72))
  const height = node.text.fontSize * 1.45
  return (
    <mesh
      name={node.id}
      position={vector(node.transform.position)}
      rotation={rotation(node.transform.rotation)}
      scale={vector(node.transform.scale)}
      userData={{ category: node.semantics.category, tags: node.semantics.tags }}
    >
      <planeGeometry args={[width, height]} />
      <meshBasicMaterial
        map={texture}
        color={node.material.color}
        transparent
        opacity={node.material.opacity}
        depthWrite={false}
        toneMapped={false}
        side={DoubleSide}
      />
    </mesh>
  )
}

function LightView({ node }: { node: LightNode }) {
  const common = {
    name: node.id,
    color: node.light.color,
    intensity: node.light.intensity,
    position: vector(node.transform.position),
  }
  if (node.subtype === 'ambient') {
    return <ambientLight name={node.id} color={node.light.color} intensity={node.light.intensity} />
  }
  if (node.subtype === 'directional') {
    return <directionalLight {...common} castShadow={node.light.castShadow} />
  }
  if (node.subtype === 'spot') {
    return (
      <spotLight
        {...common}
        distance={node.light.range}
        decay={node.light.decay}
        angle={0.72}
        penumbra={0.65}
        castShadow={node.light.castShadow}
      />
    )
  }
  return (
    <pointLight
      {...common}
      distance={node.light.range}
      decay={node.light.decay}
      castShadow={node.light.castShadow}
    />
  )
}

function GroupView({ node, children }: PropsWithChildren<{ node: GroupNode }>) {
  return (
    <group
      name={node.id}
      position={vector(node.transform.position)}
      rotation={rotation(node.transform.rotation)}
      scale={vector(node.transform.scale)}
      userData={{ category: node.semantics.category, tags: node.semantics.tags }}
    >
      {children}
    </group>
  )
}

function EffectView({ node }: { node: EffectNode }) {
  const group = useRef<Group>(null)
  const parameters = node.parameters
  useFrame((_, delta) => {
    if (group.current && parameters.rotationSpeed !== 0) {
      group.current.rotation.y += parameters.rotationSpeed * Math.min(delta, 0.05)
      group.current.rotation.z += parameters.rotationSpeed * Math.min(delta, 0.05) * 0.18
    }
  })

  if (node.subtype === 'starfield') {
    return (
      <group
        ref={group}
        name={node.id}
        position={vector(node.transform.position)}
        rotation={rotation(node.transform.rotation)}
        scale={vector(node.transform.scale)}
      >
        <Stars
          radius={parameters.radius}
          depth={parameters.spread}
          count={parameters.count}
          factor={Math.max(1.2, parameters.size * 8)}
          saturation={0.22}
          fade
          speed={Math.abs(parameters.rotationSpeed)}
        />
      </group>
    )
  }

  if (node.subtype === 'cloud_field') {
    const count = Math.min(parameters.count, 72)
    return (
      <group
        ref={group}
        name={node.id}
        position={vector(node.transform.position)}
        rotation={rotation(node.transform.rotation)}
        scale={vector(node.transform.scale)}
      >
        <Instances limit={count} range={count}>
          <sphereGeometry args={[1, 16, 10]} />
          <meshStandardMaterial
            color={parameters.color}
            emissive={parameters.secondaryColor}
            emissiveIntensity={0.08}
            transparent
            opacity={0.62}
            roughness={1}
            depthWrite={false}
          />
          {Array.from({ length: count }, (_, index) => {
            const angle = index * 2.39996
            const radius = Math.sqrt(index / Math.max(count, 1)) * parameters.spread
            return (
              <Instance
                key={node.id + '_cloud_' + index}
                position={[Math.cos(angle) * radius, Math.sin(index * 1.7) * 4, Math.sin(angle) * radius]}
                scale={[parameters.size * (1 + (index % 4) * 0.22), parameters.size * 0.55, parameters.size]}
              />
            )
          })}
        </Instances>
      </group>
    )
  }

  const common = {
    ref: group,
    name: node.id,
    position: vector(node.transform.position),
    rotation: rotation(node.transform.rotation),
    scale: vector(node.transform.scale),
  }

  if (node.subtype === 'star') {
    return (
      <group {...common}>
        <mesh>
          <sphereGeometry args={[parameters.radius, 48, 32]} />
          <meshBasicMaterial color={parameters.color} toneMapped={false} />
        </mesh>
        <mesh>
          <sphereGeometry args={[parameters.radius * 1.34, 36, 24]} />
          <meshBasicMaterial
            color={parameters.secondaryColor}
            transparent
            opacity={0.18}
            blending={AdditiveBlending}
            depthWrite={false}
            side={BackSide}
            toneMapped={false}
          />
        </mesh>
        <pointLight
          color={parameters.secondaryColor}
          intensity={parameters.intensity * 3}
          distance={parameters.spread * 3}
          decay={1.2}
        />
      </group>
    )
  }

  if (node.subtype === 'pulsar') {
    return (
      <group {...common}>
        <mesh>
          <sphereGeometry args={[parameters.radius, 40, 26]} />
          <meshBasicMaterial color={parameters.color} toneMapped={false} />
        </mesh>
        {[0, Math.PI / 2].map((angle) => (
          <mesh key={angle} rotation={[angle, 0, Math.PI / 5]}>
            <torusGeometry args={[parameters.radius * 1.7, parameters.radius * 0.08, 12, 72]} />
            <meshBasicMaterial
              color={parameters.secondaryColor}
              transparent
              opacity={0.72}
              blending={AdditiveBlending}
              depthWrite={false}
              toneMapped={false}
            />
          </mesh>
        ))}
        <mesh rotation={[0, 0, Math.PI / 5]}>
          <cylinderGeometry args={[parameters.radius * 0.08, parameters.radius * 0.42, parameters.spread, 18, 1, true]} />
          <meshBasicMaterial
            color={parameters.secondaryColor}
            transparent
            opacity={0.48}
            blending={AdditiveBlending}
            depthWrite={false}
            side={DoubleSide}
            toneMapped={false}
          />
        </mesh>
        <pointLight color={parameters.secondaryColor} intensity={parameters.intensity * 2} distance={parameters.spread * 2} />
      </group>
    )
  }

  if (node.subtype === 'black_hole') {
    return (
      <group {...common}>
        <mesh>
          <sphereGeometry args={[parameters.radius, 48, 32]} />
          <meshBasicMaterial color="#000000" />
        </mesh>
        {[1.35, 1.7, 2.1].map((scale, index) => (
          <mesh key={scale} rotation={[Math.PI / 2.5 + index * 0.08, 0.18, 0]}>
            <torusGeometry args={[parameters.radius * scale, parameters.radius * (0.16 - index * 0.025), 18, 96]} />
            <meshBasicMaterial
              color={index === 0 ? parameters.color : parameters.secondaryColor}
              transparent
              opacity={0.82 - index * 0.18}
              blending={AdditiveBlending}
              depthWrite={false}
              toneMapped={false}
            />
          </mesh>
        ))}
      </group>
    )
  }

  if (node.subtype === 'crater') {
    return (
      <group {...common}>
        <mesh>
          <cylinderGeometry args={[parameters.radius, parameters.radius * 0.78, 0.7, 64]} />
          <meshStandardMaterial color={parameters.color} roughness={0.78} metalness={0.08} />
        </mesh>
        <mesh rotation={[Math.PI / 2, 0, 0]} position={[0, 0.38, 0]}>
          <torusGeometry args={[parameters.radius * 0.86, parameters.radius * 0.16, 16, 72]} />
          <meshStandardMaterial color={parameters.secondaryColor} roughness={0.92} />
        </mesh>
        <mesh position={[0, 0.44, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <circleGeometry args={[parameters.radius * 0.72, 64]} />
          <meshStandardMaterial color={parameters.color} emissive={parameters.color} emissiveIntensity={0.2} roughness={0.3} />
        </mesh>
      </group>
    )
  }

  return (
    <group {...common}>
      <mesh castShadow receiveShadow>
        <sphereGeometry args={[parameters.radius, 48, 32]} />
        <meshStandardMaterial
          color={parameters.color}
          roughness={0.72}
          metalness={0.08}
          emissive={parameters.secondaryColor}
          emissiveIntensity={parameters.intensity * 0.05}
        />
      </mesh>
      <mesh>
        <sphereGeometry args={[parameters.radius * 1.035, 42, 28]} />
        <meshBasicMaterial
          color={parameters.secondaryColor}
          transparent
          opacity={0.14}
          side={BackSide}
          blending={AdditiveBlending}
          depthWrite={false}
        />
      </mesh>
    </group>
  )
}

const nodeRegistry: Record<SceneNode['kind'], ComponentType<RegisteredNodeProps>> = {
  primitive: ({ node }) => (node.kind === 'primitive' ? <PrimitiveView node={node} /> : null),
  text: ({ node }) => (node.kind === 'text' ? <TextView node={node} /> : null),
  light: ({ node }) => (node.kind === 'light' ? <LightView node={node} /> : null),
  group: ({ node, children }) =>
    node.kind === 'group' ? <GroupView node={node}>{children}</GroupView> : null,
  procedural: ({ node }) => (node.kind === 'procedural' ? <ProceduralView node={node} /> : null),
  asset: ({ node }) => (node.kind === 'asset' ? <AssetView node={node} /> : null),
  prefab: ({ node }) => (node.kind === 'prefab' ? <PrefabView node={node} /> : null),
  instances: ({ node }) => (node.kind === 'instances' ? <InstancesView node={node} /> : null),
  decal: ({ node }) => (node.kind === 'decal' ? <DecalView node={node} /> : null),
  effect: ({ node }) => (node.kind === 'effect' ? <EffectView node={node} /> : null),
}

export function SceneGraph({ scene, onNodeSelect }: SceneGraphProps) {
  const nodesByParent = useMemo(() => {
    const map = new Map<string | null, SceneNode[]>()
    scene.nodes.forEach((node) => {
      const siblings = map.get(node.parentId) ?? []
      siblings.push(node)
      map.set(node.parentId, siblings)
    })
    return map
  }, [scene.nodes])

  const renderNode = (node: SceneNode): React.ReactNode => {
    const Registered = nodeRegistry[node.kind]
    const children = nodesByParent.get(node.id) ?? []
    return (
      <NodeErrorBoundary key={node.id} nodeId={node.id}>
        <group
          onClick={(event) => {
            event.stopPropagation()
            onNodeSelect?.(node.id)
          }}
          userData={{ nodeId: node.id, provenance: 'provenance' in node ? node.provenance : undefined }}
        >
          <Registered node={node}>{children.map(renderNode)}</Registered>
        </group>
      </NodeErrorBoundary>
    )
  }

  return <>{(nodesByParent.get(null) ?? []).map(renderNode)}</>
}
