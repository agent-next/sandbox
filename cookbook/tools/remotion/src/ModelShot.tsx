import {useMemo} from 'react';
import {useLoader, useThree} from '@react-three/fiber';
import {GLTFLoader} from 'three/examples/jsm/loaders/GLTFLoader.js';
import {RoomEnvironment} from 'three/examples/jsm/environments/RoomEnvironment.js';
import {Box3, PMREMGenerator, Vector3, Group} from 'three';
import {ThreeCanvas} from '@remotion/three';
import {
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {MODEL_SHOT_S} from './props';

// Procedural studio environment (no assets, no network) so metallic
// PBR materials in arbitrary .glb files have something to reflect.
const StudioEnv: React.FC = () => {
  const {gl, scene} = useThree();
  useMemo(() => {
    const pmrem = new PMREMGenerator(gl);
    scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.06).texture;
  }, [gl, scene]);
  return null;
};

// Live turntable of the real .glb: studio lighting, an orbiting camera
// and the model spinning — all driven by useCurrentFrame() only
// (no useFrame(): every frame must be deterministic).
//
// useLoader suspends until the .glb is parsed; <ThreeCanvas> catches the
// suspension internally and holds the frame until the model is mounted.
const Model: React.FC<{glb: string}> = ({glb}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const camera = useThree((state) => state.camera);
  const {scene} = useLoader(GLTFLoader, staticFile(glb));

  // Fit the model: centre it and normalise to ~2 units across.
  const object = useMemo(() => {
    const clone = scene.clone(true);
    const box = new Box3().setFromObject(clone);
    const centre = box.getCenter(new Vector3());
    const size = box.getSize(new Vector3()).length() || 1;
    clone.position.sub(centre);
    const group = new Group();
    group.add(clone);
    group.scale.setScalar(2.4 / size);
    return group;
  }, [scene]);

  const total = MODEL_SHOT_S * fps;
  const orbit = (frame / total) * Math.PI * 0.75 + Math.PI * 0.18;
  const radius = 3.4;
  camera.position.set(
    Math.sin(orbit) * radius,
    0.9 + Math.sin((frame / total) * Math.PI) * 0.5,
    Math.cos(orbit) * radius,
  );
  camera.lookAt(0, 0, 0);

  return (
    <primitive
      object={object}
      rotation={[Math.PI / 2.6, (frame / total) * Math.PI * 1.4, 0]}
    />
  );
};

export const ModelShot: React.FC<{glb: string}> = ({glb}) => {
  const {width, height} = useVideoConfig();
  return (
    <ThreeCanvas
      width={width}
      height={height}
      camera={{position: [0, 1, 3.4], fov: 42}}
      style={{backgroundColor: '#070b14'}}
    >
      <StudioEnv />
      <ambientLight intensity={0.5} />
      <directionalLight position={[4, 6, 5]} intensity={1.6} />
      <directionalLight position={[-5, 2, -4]} intensity={0.7} color="#2EC4B6" />
      <pointLight position={[0, -3, 2]} intensity={26} color="#F58518" />
      <gridHelper args={[14, 28, 0x2a6a60, 0x18282f]} position={[0, -1.4, 0]} />
      <Model glb={glb} />
    </ThreeCanvas>
  );
};
