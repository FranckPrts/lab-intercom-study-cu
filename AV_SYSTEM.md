# AV system in the study room

## Questions

### General

- [ ] Is there a diagram or equipment list of the room's AV system? Can we get
      a copy?
- [ ] Who manages it (AV team, IT, the lab)? Who do we contact when something
      does not work, and who can change settings?

### Cameras

- [ ] How many cameras, which make and model, and where are they? Can they be
      moved or aimed (PTZ: pan, tilt, zoom)? Can positions be saved as presets
      so every session has the same framing?
- [ ] The Ethernet cable from each camera: what is it?
  - NDI (full bandwidth) or NDI|HX (compressed)?
  - RTSP / ONVIF (IP camera, like a security camera)?
  - SRT, Dante AV, or another protocol?
  - HDBaseT (HDMI or SDI over an Ethernet-type cable, not a network)?
  - Is it PoE (powered over the same cable)?
- [ ] Resolution and frame rate. Is the frame rate fixed (e.g. 25, 30, 50 or
      60 fps), or can it vary? Can we choose it?
- [ ] Where does the video go: a recording PC, an NVR, a video switcher or
      software (vMix, OBS, TriCaster, ...)? What records it, in which file
      format, and where are the files stored?
- [ ] Does the recording include timestamps or timecode per frame? Based on
      which clock? // Do the cameras and the recorder sync their clocks (NTP or PTP)? To
      which time server?
- [ ] Can we receive the camera streams directly on our own computer (e.g.
      with NDI Tools or OBS)? Is there a login or licence needed?
- [ ] Do the cameras record sound too, and from which microphone?
- [ ] Do we have photodiode?

### Microphones and sound

- [ ] Which microphones are in the room (ceiling, table/boundary, lavalier,
      headset), how many, and where?
- [ ] What do the microphones go into: a mixer, a DSP, an audio interface? Is
      it Dante (audio over the network)?
- [ ] Is processing applied (echo cancellation, noise reduction, automatic
      gain)? Can it be turned off to get the raw signal?
- [ ] Sample rate, and what sets the audio clock (Dante/PTP, the mixer, the
      PC)?
- [ ] Is there a free input where we could feed a sync signal (a beep or
      timecode audio) so it ends up in their recording?
- [ ] (for us, experiementer) Speakers in the room, and can our main computer play sound through them?

### Network

- [ ] Is the AV equipment on its own network, or on the university network?
      Is it a separate VLAN? Managed switches?
- [ ] Can we plug in our own router and devices (tablets, main computer)?
- [ ] Can we make DHCP reservations?
- [ ] Is multicast allowed, and are devices allowed to see each other (no
      client isolation)? NDI uses mDNS (or an NDI Discovery Server) to find
      sources; LSL uses UDP multicast/broadcast to find streams.

### Electrical noise (for the EEG)

- [ ] Can we switch off power outlets near the participants? Are displays,
      PoE switches or power supplies close to where participants sit?