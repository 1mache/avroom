# Avroom

The product language for the room the user edits, the objects in it, and the actions that change them. Code identifiers stay in the codebase; this file is the glossary.

## Language

### Places

**Project Selector**:
The home screen. A list of Projects.
_Avoid_: Dashboard, Room Selector

**Room Selector**:
The screen listing one Project's rooms. Entered by opening a Project from Project Selector.
_Avoid_: Dashboard, Project Selector

**Room Upload**:
The file-intake screen between Room Selector and Room Workspace. Creates a room.
_Avoid_: Upload (as a screen name)

**Room Workspace**:
The editor for one room.
_Avoid_: Workspace (as a screen name)

**Debug Dashboard**:
The inspection screen. No room is created and nothing is saved.
_Avoid_: Debug (as a screen name)

**Stage**:
The surface under the toolbar where the room is shown.
_Avoid_: canvas (the background file), the window

### Spaces

**natural-image**:
Pixel coordinates on the Origin Photo file. Origin is the file's top-left.
_Avoid_: "image space", display pixels

**stage-local**:
CSS-pixel coordinates inside the stage element. Origin is the stage's top-left.
_Avoid_: screen coordinates, client

**rendered-rect**:
Where the Origin Photo or Background is actually painted inside the stage after contain-fit. Origin is the stage's top-left.
_Avoid_: the stage itself, the photo's file rect

**letterbox**:
Stage pixels around the rendered-rect. A pointer there is not on the picture.
_Avoid_: "outside the image", "off the photo"

**client**:
Pointer coordinates in the browser viewport. Origin is the viewport's top-left.
_Avoid_: stage-local, natural-image

**offset**:
A displacement of a cutout in natural-image pixels from its native placement. Not a separate origin.
_Avoid_: position, location, shifted

### Nouns

**Project**:
A named group of Rooms, owned by a user. Its Project Selector card shows its most recently edited Room's Preview.
_Avoid_: Session, folder, workspace

**Room**:
One Origin Photo plus every object and background change made to it. Belongs to exactly one Project.
_Avoid_: Session, uid, image_id, project (lowercase; capitalized Project is the group above it)

**Origin Photo**:
The original uploaded picture. Immutable.
_Avoid_: Photo, original image, the current background

**Background**:
The current room picture with removed regions filled in. Sits under every object.
_Avoid_: canvas, Origin Photo, the composed stage view

**Object**:
One furniture or item in the room: identity, cutout, offset, and name.
_Avoid_: mask, the PNG file alone, 3D render

**Cutout**:
The transparent PNG of an object's pixels (alpha 0 outside the object).
_Avoid_: the object itself, the mask, the background hole

**Source Cutout**:
The original extracted cutout PNG for an object. Rotation never replaces this file.
_Avoid_: Pristine, original (when meaning this file)

**Mask**:
A binary region marking which pixels are the thing. Used to cut and to fill.
_Avoid_: cutout, object

**Candidate**:
One mask option shown in the picker before commit.
_Avoid_: a finalized object, mask (once committed)

**Segmentation seed**:
A click point that starts segmentation.
_Avoid_: Seed, click, drag, erase loop

**Job**:
One queued unit of server work: segment, inpaint, erase, or build 3D.
_Avoid_: spinner, toolbar mode, "in flight" as a noun

**Batch**:
A local list of armed jobs in Room Workspace. Nothing in a Batch hits the server until Approve.
_Avoid_: queue (as the product noun), pending work

**Copy**:
An object created from another object in the same room. Also the action that creates it.
_Avoid_: Clone, Duplicate

**3D render**:
The object's 3D mesh, used as the rotation angle picker.
_Avoid_: GLB, "the model" (when meaning this mesh)

**Preview**:
The Room Selector card thumbnail of a room as left.
_Avoid_: Snapshot, rotation capture

**Snapshot**:
A downloaded still of the Background plus visible objects.
_Avoid_: Preview, 3D-viewer capture

**Object Selector**:
The right-edge list of objects in Room Workspace.
_Avoid_: Rail, ObjectRail, ObjectPanel, toolbar

### States

**armed**:
A tool is waiting for the next pointer gesture.
_Avoid_: selected (for tools), active, on

**selected**:
An object is the target of rotate, copy, delete, or smart-paste. Independent of hidden.
_Avoid_: visible, focused

**hidden**:
An object is not drawn and not hittable. Local only; not delete.
_Avoid_: deleted, removed

**pending**:
A rotation is showing a 3D-viewer capture while the synthesized view has not landed.
_Avoid_: queued (that is a job status)

**source**:
The Source Cutout is showing, not a rotated view.
_Avoid_: pristine, original

### Verbs

**Upload**:
Create a room from an Origin Photo file and open Room Workspace.
_Avoid_: new session, import (for the room itself)

**Cut out**:
Turn a segmentation seed, seeds, or a box into an object and a filled background hole.
_Avoid_: remove, segment (as the user action), click-to-remove

**Erase**:
Fill lassoed background pixels without creating an object.
_Avoid_: cut out, delete

**Batch**:
Arm cutouts, erases, area boxes, and 3D builds into a local list, reorder and edit them, then Approve to send. Seeds on one armed cut out are one object.
_Avoid_: queue (as the product verb), submit

**Select**:
Make an object the selected object, from the stage or the Object Selector.
_Avoid_: click (when meaning this), highlight

**Drag**:
Change an object's offset. Persisted on pointer-up.
_Avoid_: move, place (when meaning offset only)

**Copy**:
Create a Copy of the selected object, nudged aside. Background unchanged.
_Avoid_: Duplicate, Clone

**Copy room**:
Create a new Room in the same Project that clones the Origin Photo, Background, Preview, and every visible object (including 3D renders). Named like object copies (`Living room-copy`, then `-copy1`).
_Avoid_: Duplicate room, Clone session, Copy (alone — that is the object action)

**Add object**:
Bring a user-supplied PNG into the room as a new overlay object. Background unchanged.
_Avoid_: Import

**Delete**:
Permanently remove an object. The background hole stays.
_Avoid_: hide, erase, undo

**Hide** / **Show**:
Toggle whether an object is drawn. Not delete.
_Avoid_: delete, remove

**Rename**:
Change the display name of a project, a room, or an object.
_Avoid_: label, title (as the verb)

**Rotate**:
Open the 3D angle picker on the selected object and commit a new 2D view. The Source Cutout is untouched.
_Avoid_: orbit (the gesture is part of rotate, not a separate product verb)

**Smart-paste**:
Place the selected object at a drop point. When armed, runs only the steps enabled in toolbar settings: scale by POV (depth-proportional rescale) and smart rotate (infer mesh pose from surface normals).
_Avoid_: drag (when this extra step runs)

**Scale by POV**:
Smart-paste step that rescales the object to match depth at the drop point.
_Avoid_: rescale (as the product verb alone)

**Smart rotate**:
Smart-paste step that infers a mesh-orbit pose from normals at the source cutout center vs the drop point.
_Avoid_: auto-rotate (as the product verb)

**Backtrack**:
Restore the previous background stage of the room. Later objects are hidden.
_Avoid_: Undo (as the product verb), reset

**Forward**:
Restore the next background stage of the room.
_Avoid_: Redo (as the product verb)

**Reset**:
Clear offset, scale, and rotation on one object.
_Avoid_: backtrack, show original

### Processes

**Cut out**:
Arm a tool, place segmentation seed(s), segment into candidates, pick one, inpaint. Result: an object and a filled Background.
_Avoid_: remove, the click pipeline

**Erase**:
Lasso a region and fill those background pixels. No object is created.
_Avoid_: cut out

**Rotate**:
Obtain a 3D render, orbit, commit a novel view. The Source Cutout stays.
_Avoid_: 3D preview (as the product)

**Place**:
Drag to change offset. With smart-paste armed, the drop also runs whichever smart-paste steps are on in settings (scale by POV, smart rotate).
_Avoid_: move, position

**History**:
Each inpaint or erase commits a background stage. Backtrack and Forward move among stages.
_Avoid_: undo stack (as the product name)
