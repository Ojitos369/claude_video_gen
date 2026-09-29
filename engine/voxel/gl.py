# Offscreen OpenGL (moderngl; EGL on Linux, WGL on Windows) voxel renderer. Everything is a pure function of time t:
# scene A -> scene B morph, per-voxel motion, audio-reactive lights, sun shadows (PCF), sky, height fog, bloom, sun rays, ACES.
import math
import numpy as np
import moderngl

NOISE = """
float h21(vec2 p){ p = fract(p*vec2(123.34, 456.21)); p += dot(p, p+45.32); return fract(p.x*p.y); }
float vnoise(vec2 p){ vec2 i=floor(p), f=fract(p); f=f*f*(3.-2.*f);
  return mix(mix(h21(i), h21(i+vec2(1,0)), f.x), mix(h21(i+vec2(0,1)), h21(i+vec2(1,1)), f.x), f.y); }
float fbm2(vec2 p){ float s=0., a=.5; for(int i=0;i<5;i++){ s+=a*vnoise(p); p=p*2.03+17.1; a*=.5; } return s; }
"""

VOX_VS = """
#version 330
in vec3 in_pos; in vec3 in_nrm;
in vec4 a_pos; in vec4 a_col; in vec4 a_nrm; in vec4 a_misc; in vec4 a_lit; in vec4 a_mot;
in vec4 b_pos; in vec4 b_col; in vec4 b_nrm; in vec4 b_misc; in vec4 b_lit; in vec4 b_mot;
in vec4 rnd;
uniform mat4 uVP; uniform vec3 uCam, uMagic; uniform float uMorph, uTime, uVS, uR, uBass; uniform int uMode;
out vec3 vAlb; out vec3 vN; out vec3 vFace; out vec3 vP; out vec4 vMisc; out vec4 vLit; out float vAO; out float vMat; out vec3 vMagic;
vec2 rot(vec2 v, float a){ float c=cos(a), s=sin(a); return vec2(c*v.x-s*v.y, s*v.x+c*v.y); }
vec3 motion(vec3 p, vec4 m){
  int t = int(m.x+.5); float a = uTime*m.w;
  if(t==1) p.xz = m.yz + rot(p.xz-m.yz, a);
  else if(t==2) p.xy = m.yz + rot(p.xy-m.yz, a);
  else if(t==3) p.yz = m.yz + rot(p.yz-m.yz, a);
  else if(t==4) p.y += m.y*sin(uTime*m.w + m.z + p.x*0.05);
  return p; }
vec3 hue(float h){ return clamp(abs(fract(h+vec3(0.,2./3.,1./3.))*6.-3.)-1., 0., 1.); }
void main(){
  // uMode 0: scene A disassembles upward into sparks; 1: scene B assembles (falls into place); 2: B static.
  // A radial wave from the centre drives both, B trailing A so every spot is rebuilt right after it is cleared.
  bool isA = uMode == 0;
  vec4 pos = isA ? a_pos : b_pos, col = isA ? a_col : b_col, nrm4 = isA ? a_nrm : b_nrm, misc = isA ? a_misc : b_misc;
  vec4 lit = isA ? a_lit : b_lit, mot = isA ? a_mot : b_mot;
  vec3 n = nrm4.xyz*2.-1.;
  vec3 P = motion(pos.xyz + n*pos.w*uVS*0.5, mot);
  float rad = clamp(length(P.xz)/uR, 0., 1.);
  float p = 1.;
  if(uMode == 0) p = clamp((uMorph - (0.45*rad + 0.15*rnd.x))/0.3, 0., 1.);
  else if(uMode == 1) p = clamp((uMorph - (0.10 + 0.45*rad + 0.15*rnd.x))/0.3, 0., 1.);
  float e = p*p*(3.-2.*p);
  float k = isA ? e : 1. - e;           // 0 = in place, 1 = fully away
  float s = sin(3.14159*k);
  vec3 away = isA ? vec3(rot(vec2(1.,0.), rnd.y*6.28)*(1.5+2.5*rnd.z)*k, -(2.+6.*rnd.z)*k)   // A crumbles and sinks
                  : vec3(0., (6.+12.*rnd.z)*k, 0.);                                          // B drops into place
  P += away;
  float size = uVS * misc.w * pow(1. - k, 1.5);
  size *= smoothstep(1.5, 8.0, distance(P, uCam));
  vec3 lp = in_pos;
  if(k > 0.001){ float ang = k*4.*rnd.w; lp.xy = rot(lp.xy, ang); lp.yz = rot(lp.yz, ang*.7); }
  vec3 wp = P + lp*size*1.02;
  vP = wp; vFace = in_nrm; vN = n;
  vAlb = pow(col.rgb, vec3(2.2)); vAO = col.a; vMisc = misc; vLit = lit;
  vMat = floor(nrm4.w*255./10. + .5);
  vMagic = mix(uMagic, hue(rnd.w), 0.2) * s * (0.12 + 0.3*uBass);
  gl_Position = uVP * vec4(wp, 1.);
}
"""

VOX_FS = """
#version 330
in vec3 vAlb; in vec3 vN; in vec3 vFace; in vec3 vP; in vec4 vMisc; in vec4 vLit; in float vAO; in float vMat; in vec3 vMagic;
uniform vec3 uCam, uSunDir, uSunCol, uAmb, uHor, uFog; uniform float uFogD, uFogH, uFogF, uGlow, uTime;
uniform float uBass, uMid, uHigh, uBeat, uChase, uShock, uShockR;
uniform mat4 uLVP; uniform sampler2DShadow uShadow;
out vec4 frag;
""" + NOISE + """
const vec2 PD[12] = vec2[](vec2(-.326,-.406),vec2(-.840,-.074),vec2(-.696,.457),vec2(-.203,.621),vec2(.962,-.195),vec2(.473,-.480),
  vec2(.519,.767),vec2(.185,-.893),vec2(.507,.064),vec2(.896,.412),vec2(-.322,-.933),vec2(-.792,-.598));
float shadow(vec3 p, vec3 n){
  vec4 l = uLVP * vec4(p + n*0.25, 1.); vec3 c = l.xyz/l.w*.5+.5;
  if(c.x<0.||c.x>1.||c.y<0.||c.y>1.) return 1.;
  float a = h21(gl_FragCoord.xy)*6.2831; mat2 R = mat2(cos(a),-sin(a),sin(a),cos(a)); float s=0.;
  for(int i=0;i<12;i++) s += texture(uShadow, vec3(c.xy + R*PD[i]*(2.2/4096.), c.z - 0.0015));
  return s/12.; }
void main(){
  vec3 N = normalize(mix(vFace, vN, 0.85));
  vec3 V = normalize(uCam - vP), L = normalize(uSunDir);
  float sh = shadow(vP, N);
  float grp = floor(vMisc.y*255./60.+.5), ph = vMisc.z, glow = vMisc.x;
  vec3 sun = uSunCol * max(dot(N, L), 0.) * sh;
  float hemi = .55 + .45*N.y;
  vec3 amb = uAmb * (.3 + .7*vLit.a) * (.35 + .65*vAO) * hemi;
  vec3 bounce = uHor * .25 * (1. - N.y*.5) * vAO;
  vec3 loc = vLit.rgb*vLit.rgb * (.9 + .6*uBass + .3*uBeat) * 3.;
  vec3 col = vAlb * (sun + amb + bounce + loc);
  vec3 H = normalize(L + V);
  if(vMat == 7. || vMat == 8.){   // metal / brass: specular + sky reflection
    col += uSunCol * pow(max(dot(N,H),0.), vMat==8.?60.:30.) * sh * (vMat==8.? vAlb*2.2 : vec3(.6));
    col += uAmb * vAlb * .35 * pow(1.-max(dot(N,V),0.), 3.);
  } else if(vMat == 2.){   // water
    float n = vnoise(vP.xz*.6 + uTime*.4);
    vec3 Nw = normalize(vec3((n-.5)*.4, 1., (vnoise(vP.zx*.6 - uTime*.35)-.5)*.4));
    float fr = .04 + .96*pow(1.-max(dot(Nw,V),0.), 5.);
    col = mix(col, uHor*1.1, fr*.7) + uSunCol * pow(max(dot(Nw, normalize(L+V)),0.), 120.) * sh * 1.5;
  } else if(vMat == 4.){   // glass
    col += uSunCol * pow(max(dot(N,H),0.), 80.) * sh + uAmb*.15;
  } else if(vMat == 5.){   // steam
    col = vAlb * (uAmb*.9 + uSunCol*.5*sh + loc);
  } else if(vMat == 6.){   // lava / furnace
    col += vAlb * (1.2 + .8*vnoise(vP.xz*.5 + uTime*.6)) * (1. + .6*uBass);
  }
  // audio-reactive emission by light group
  float k = grp < .5 ? (.35 + 1.1*uBass) : grp < 1.5 ? (.35 + 1.0*uMid) :
            grp < 2.5 ? (.2 + 1.4*uHigh*(.5+.5*sin(uTime*9. + ph*40.))) :
            (.25 + 1.6*exp(-6.*fract(uChase*.25 - ph)));
  col += vAlb * glow * k * uGlow * 2.2;
  col += vMagic;
  // shock ring on scene changes / accents
  float d = length(vP.xz);
  col += vec3(1., .75, .4) * uShock * exp(-pow((d - uShockR)*.35, 2.)) * .8;
  // height fog + sun scatter
  float dist = length(vP - uCam); float dy = vP.y - uCam.y;
  float a = uFogD * exp(-uFogF*(uCam.y - uFogH));
  float kf = abs(dy) > .01 ? (1. - exp(-uFogF*dy))/(uFogF*dy) : 1.;
  float f = 1. - exp(-(a*kf + uFogD*.25) * dist);
  vec3 fc = uFog + uSunCol*.35*pow(max(dot(-V, L), 0.), 8.);
  frag = vec4(mix(col, fc, clamp(f, 0., 1.)), 1.);
}
"""

SHADOW_FS = """
#version 330
void main(){}
"""

QUAD_VS = """
#version 330
in vec2 in_p; out vec2 uv;
void main(){ uv = in_p*.5+.5; gl_Position = vec4(in_p, 0., 1.); }
"""

SKY_FS = """
#version 330
in vec2 uv; out vec4 frag;
uniform mat4 uInvVP; uniform vec3 uCam, uSunDir, uSunCol, uZen, uHor, uFloor, uMtn, uFog; uniform float uMtnH, uClouds, uStars, uTime, uHigh, uSunVis;
""" + NOISE + """
void main(){
  vec4 w = uInvVP * vec4(uv*2.-1., 1., 1.); vec3 d = normalize(w.xyz/w.w - uCam);
  vec3 L = normalize(uSunDir);
  float y = d.y;
  vec3 col = mix(uHor, uZen, pow(clamp(y, 0., 1.), .55));
  float sd = max(dot(d, L), 0.);
  col += uSunCol * (pow(sd, 8.)*.35 + pow(sd, 90.)*.8) ;
  col += uSunCol * smoothstep(.9985, .9992, sd) * 6. * uSunVis;
  if(uStars > 0.){ vec2 g = floor(d.xz/(abs(d.y)+.3)*140.); float s = h21(g); col += vec3(1.) * step(.995, s) * uStars * (.6+.4*sin(uTime*3.+s*50.+uHigh*4.)) * smoothstep(0.,.2,y); }
  if(y > 0.){   // smoggy clouds
    vec2 p = d.xz/(y+.12); float n = fbm2(p*1.2 + vec2(uTime*.01, 0.));
    float c = smoothstep(.45, .8, n) * uClouds * smoothstep(0., .25, y);
    vec3 cc = mix(uHor*1.05, uSunCol*1.2, pow(sd, 3.)*.7) * (.75 + .25*n);
    col = mix(col, cc, c);
  }
  // distant skyline / mountains (continuous azimuth coordinates)
  vec2 az = normalize(d.xz);
  float n1 = fbm2(az*3.1 + 5.), n2 = floor(fbm2(az*9. + 11.)*7.)/7.;
  float hm = uMtnH*(.35 + .9*n1) + uMtnH*.55*n2*step(.5, fbm2(az*23.));
  if(y < hm && y > -.05){ col = mix(uMtn, uFog, .45 + .4*(1.-(y+.05)/(hm+.05))); }
  if(y < -.0){   // infinite floor (cloud sea / haze)
    vec2 p = d.xz/(-y+.05); float n = fbm2(p*.5 + uTime*.02);
    col = mix(uFloor*(.8+.35*n), uFog, clamp(1.+y*6., 0., 1.)*.6);
  }
  col = mix(col, uFog, exp(-abs(y)*14.)*.55);   // horizon haze
  frag = vec4(col, pow(sd, 40.)*uSunVis);
}
"""

BRIGHT_FS = """
#version 330
in vec2 uv; out vec4 frag; uniform sampler2D uTex;
void main(){ vec3 c = texture(uTex, uv).rgb; float l = dot(c, vec3(.2126,.7152,.0722)); frag = vec4(c * smoothstep(1.0, 1.6, l), 1.); }
"""
BLUR_FS = """
#version 330
in vec2 uv; out vec4 frag; uniform sampler2D uTex; uniform vec2 uDir;
void main(){ vec3 s = texture(uTex, uv).rgb*.227;
  s += (texture(uTex, uv+uDir*1.385).rgb + texture(uTex, uv-uDir*1.385).rgb)*.316;
  s += (texture(uTex, uv+uDir*3.231).rgb + texture(uTex, uv-uDir*3.231).rgb)*.070;
  frag = vec4(s, 1.); }
"""
FINAL_FS = """
#version 330
in vec2 uv; out vec4 frag;
uniform sampler2D uHDR, uBloom, uBright; uniform float uExp, uBloomK, uRays, uFade, uTime; uniform vec2 uSunUV;
vec3 aces(vec3 x){ return clamp((x*(2.51*x+.03))/(x*(2.43*x+.59)+.14), 0., 1.); }
float h(vec2 p){ return fract(sin(dot(p, vec2(12.9898,78.233)))*43758.5453); }
void main(){
  vec3 c = texture(uHDR, uv).rgb + texture(uBloom, uv).rgb*uBloomK;
  if(uRays > 0.){ vec2 dlt = (uv - uSunUV)/32.; vec2 q = uv; vec3 r = vec3(0.); float w = 1.;
    for(int i=0;i<32;i++){ q -= dlt; r += texture(uBright, q).rgb*w; w *= .95; } c += r/32.*uRays; }
  c *= uExp;
  float l = dot(c, vec3(.2126,.7152,.0722)); c = mix(c, vec3(l), .08);
  c = aces(c);
  c = pow(c, vec3(1./2.2));
  vec2 v = uv - .5; c *= 1. - dot(v, v)*.55;
  c += (h(uv*1000. + uTime) - .5)*.012;
  frag = vec4(c*uFade, 1.);
}
"""

def cube_vertices():
    v = []
    faces = [((1, 0, 0), (0, 1, 0), (0, 0, 1)), ((-1, 0, 0), (0, 0, 1), (0, 1, 0)), ((0, 1, 0), (0, 0, 1), (1, 0, 0)),
             ((0, -1, 0), (1, 0, 0), (0, 0, 1)), ((0, 0, 1), (1, 0, 0), (0, 1, 0)), ((0, 0, -1), (0, 1, 0), (1, 0, 0))]
    for n, a, b in faces:
        n, a, b = np.array(n, float), np.array(a, float), np.array(b, float)
        c = n * .5
        q = [c - a * .5 - b * .5, c + a * .5 - b * .5, c + a * .5 + b * .5, c - a * .5 + b * .5]
        for i in (0, 1, 2, 0, 2, 3): v += list(q[i]) + list(n)
    return np.array(v, np.float32)

def perspective(fovy, aspect, near, far):
    f = 1 / math.tan(math.radians(fovy) / 2)
    return np.array([[f / aspect, 0, 0, 0], [0, f, 0, 0], [0, 0, (far + near) / (near - far), 2 * far * near / (near - far)], [0, 0, -1, 0]], np.float32)

def ortho(l, r, b, t, n, f):
    return np.array([[2 / (r - l), 0, 0, -(r + l) / (r - l)], [0, 2 / (t - b), 0, -(t + b) / (t - b)], [0, 0, -2 / (f - n), -(f + n) / (f - n)], [0, 0, 0, 1]], np.float32)

def look_at(eye, tgt, up=(0, 1, 0)):
    eye, tgt, up = np.array(eye, float), np.array(tgt, float), np.array(up, float)
    f = tgt - eye; f /= np.linalg.norm(f)
    s = np.cross(f, up); s /= np.linalg.norm(s) + 1e-9
    u = np.cross(s, f)
    m = np.eye(4, dtype=np.float32); m[0, :3], m[1, :3], m[2, :3] = s, u, -f
    m[:3, 3] = -m[:3, :3] @ eye
    return m

class Renderer:
    def __init__(self, W, H, N, R, vs, shadow_size=4096, samples=4):
        self.W, self.H, self.N, self.R, self.vs = W, H, N, R, vs
        import sys   # headless GL: EGL on Linux (no X needed); the default (WGL / CGL) on Windows and macOS
        self.ctx = ctx = moderngl.create_standalone_context(backend="egl") if sys.platform.startswith("linux") else moderngl.create_standalone_context()
        ctx.enable(moderngl.DEPTH_TEST | moderngl.CULL_FACE)
        self.prog = ctx.program(vertex_shader=VOX_VS, fragment_shader=VOX_FS)
        self.sprog = ctx.program(vertex_shader=VOX_VS, fragment_shader=SHADOW_FS)
        self.sky = ctx.program(vertex_shader=QUAD_VS, fragment_shader=SKY_FS)
        self.bright = ctx.program(vertex_shader=QUAD_VS, fragment_shader=BRIGHT_FS)
        self.blur = ctx.program(vertex_shader=QUAD_VS, fragment_shader=BLUR_FS)
        self.final = ctx.program(vertex_shader=QUAD_VS, fragment_shader=FINAL_FS)
        self.cube = ctx.buffer(cube_vertices())
        self.rnd = ctx.buffer(np.random.default_rng(1).random((N, 4)).astype(np.float32))
        quad = ctx.buffer(np.array([-1, -1, 1, -1, -1, 1, 1, 1], np.float32))
        self.quads = {p: ctx.vertex_array(p, [(quad, "2f", "in_p")]) for p in (self.sky, self.bright, self.blur, self.final)}
        # targets
        self.msaa = ctx.framebuffer([ctx.renderbuffer((W, H), 4, samples=samples, dtype="f2")], ctx.depth_renderbuffer((W, H), samples=samples))
        self.hdr_t = ctx.texture((W, H), 4, dtype="f2"); self.hdr = ctx.framebuffer([self.hdr_t])
        h2, h4 = (W // 2, H // 2), (W // 4, H // 4)
        self.br_t = ctx.texture(h2, 4, dtype="f2"); self.br = ctx.framebuffer([self.br_t])
        self.b1_t = ctx.texture(h4, 4, dtype="f2"); self.b1 = ctx.framebuffer([self.b1_t])
        self.b2_t = ctx.texture(h4, 4, dtype="f2"); self.b2 = ctx.framebuffer([self.b2_t])
        for t in (self.hdr_t, self.br_t, self.b1_t, self.b2_t): t.repeat_x = t.repeat_y = False
        self.out_t = ctx.texture((W, H), 3); self.out = ctx.framebuffer([self.out_t])
        self.sh_t = ctx.depth_texture((shadow_size, shadow_size)); self.sh_t.compare_func = "<="
        self.sh_t.filter = (moderngl.LINEAR, moderngl.LINEAR); self.sh_t.repeat_x = self.sh_t.repeat_y = False
        self.sh = ctx.framebuffer(depth_attachment=self.sh_t)
        self.bufs, self.vaos = {}, {}

    FORMATS = [("pos", "4f"), ("col", "4f1"), ("nrm", "4f1"), ("misc", "4f1"), ("lit", "4f1"), ("mot", "4f2")]

    def upload(self, key, pack):
        if key in self.bufs: return
        if len(self.bufs) >= 4:   # keep at most 4 scenes on the GPU
            old = next(iter(self.bufs))
            for b in self.bufs.pop(old).values(): b.release()
            for k in [k for k in self.vaos if old in k]:
                for v in self.vaos.pop(k): v.release()
        self.bufs[key] = {name: self.ctx.buffer(np.ascontiguousarray(pack[name])) for name, _ in self.FORMATS}

    def _vao(self, ka, kb):
        if (ka, kb) not in self.vaos:
            A, B = self.bufs[ka], self.bufs[kb]
            def content(prog):   # attributes the compiler optimised away must be left out / padded
                c = [(self.cube, "3f " + ("3f" if "in_nrm" in prog else "12x"), *(["in_pos", "in_nrm"] if "in_nrm" in prog else ["in_pos"]))]
                for pre, S in (("a_", A), ("b_", B)):
                    c += [(S[name], fmt + "/i", pre + name) for name, fmt in self.FORMATS if pre + name in prog]
                if "rnd" in prog: c.append((self.rnd, "4f/i", "rnd"))
                return c
            self.vaos[(ka, kb)] = (self.ctx.vertex_array(self.prog, content(self.prog)), self.ctx.vertex_array(self.sprog, content(self.sprog)))
        return self.vaos[(ka, kb)]

    @staticmethod
    def _set(prog, **u):
        for k, v in u.items():
            if k in prog:
                prog[k].value = tuple(map(float, np.ravel(v))) if np.size(v) > 1 else float(v)

    def render(self, ka, kb, morph, t, cam_pos, cam_tgt, look, audio, fovy=60.0, fade=1.0, shock=(0.0, 0.0)):
        ctx, W, H = self.ctx, self.W, self.H
        view = look_at(cam_pos, cam_tgt); proj = perspective(fovy, W / H, 0.3, 900.0)
        vp = proj @ view
        L = np.array(look["sunDir"], float); L /= np.linalg.norm(L)
        lview = look_at(L * 160, (0, 0, 0), (0, 1, 0) if abs(L[1]) < .95 else (0, 0, 1))
        lvp = ortho(-self.R * 1.25, self.R * 1.25, -self.R * 1.25, self.R * 1.25, 1, 340) @ lview
        vao, svao = self._vao(ka, kb)
        common = dict(uMorph=morph, uTime=t, uVS=self.vs, uR=self.R, uBass=audio["bass"], uMagic=look.get("magic", (1.0, .6, .25)))
        # shadow pass
        self.sh.use(); self.sh.clear(depth=1.0); ctx.viewport = (0, 0) + self.sh_t.size
        ctx.disable(moderngl.CULL_FACE)
        self._set(self.sprog, uVP=lvp.T, uCam=L * 160, **common)
        modes = (2,) if morph >= 1 else (0, 1)
        for md in modes:
            self.sprog["uMode"].value = md; svao.render(moderngl.TRIANGLES, instances=self.N)
        # main pass: sky, then voxels
        self.msaa.use(); ctx.viewport = (0, 0, W, H); self.msaa.clear(0, 0, 0, 1, depth=1.0)
        ctx.disable(moderngl.DEPTH_TEST)
        self._set(self.sky, uInvVP=np.linalg.inv(vp).T, uCam=cam_pos, uSunDir=L, uSunCol=look["sunCol"], uZen=look["zen"], uHor=look["hor"],
                  uFloor=look["floor"], uMtn=look["mtn"], uFog=look["fog"], uMtnH=look["mtnH"], uClouds=look["clouds"], uStars=look["stars"],
                  uTime=t, uHigh=audio["high"], uSunVis=look["sunVis"])
        self.quads[self.sky].render(moderngl.TRIANGLE_STRIP)
        ctx.enable(moderngl.DEPTH_TEST)
        self.sh_t.use(0)
        self._set(self.prog, uVP=vp.T, uCam=cam_pos, uSunDir=L, uSunCol=np.array(look["sunCol"]) * look["sunI"], uAmb=look["amb"], uHor=look["hor"],
                  uFog=look["fog"], uFogD=look["fogD"], uFogH=look["fogH"], uFogF=look["fogF"], uGlow=look["glow"], uMid=audio["mid"],
                  uHigh=audio["high"], uBeat=audio["beat"], uChase=audio["chase"], uShock=shock[0], uShockR=shock[1], uLVP=lvp.T, **common)
        self.prog["uShadow"].value = 0
        for md in modes:
            self.prog["uMode"].value = md; vao.render(moderngl.TRIANGLES, instances=self.N)
        ctx.enable(moderngl.CULL_FACE)
        ctx.copy_framebuffer(self.hdr, self.msaa)
        # post
        ctx.disable(moderngl.DEPTH_TEST)
        self.br.use(); ctx.viewport = (0, 0) + self.br_t.size; self.hdr_t.use(0); self.bright["uTex"].value = 0
        self.quads[self.bright].render(moderngl.TRIANGLE_STRIP)
        src = self.br_t
        for i in range(3):
            for fb, tex, d in ((self.b1, self.b1_t, (1, 0)), (self.b2, self.b2_t, (0, 1))):
                fb.use(); ctx.viewport = (0, 0) + tex.size; src.use(0); self.blur["uTex"].value = 0
                self.blur["uDir"].value = (d[0] / tex.size[0] * (1 + i), d[1] / tex.size[1] * (1 + i))
                self.quads[self.blur].render(moderngl.TRIANGLE_STRIP); src = tex
        s = vp @ np.array([*(np.array(cam_pos) + L * 500), 1.0]); suv = (s[:2] / s[3]) * .5 + .5
        rays = look["rays"] * (1.0 if s[3] > 0 else 0.0)
        self.out.use(); ctx.viewport = (0, 0, W, H)
        self.hdr_t.use(0); self.b2_t.use(1); self.br_t.use(2)
        self.final["uHDR"].value, self.final["uBloom"].value, self.final["uBright"].value = 0, 1, 2
        self._set(self.final, uExp=look["exp"], uBloomK=look["bloom"], uRays=rays, uFade=fade, uTime=t, uSunUV=suv)
        self.quads[self.final].render(moderngl.TRIANGLE_STRIP)
        ctx.enable(moderngl.DEPTH_TEST)
        return self.out.read(components=3)   # bottom-up rows
