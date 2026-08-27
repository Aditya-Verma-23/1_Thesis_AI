export class CustomResize {
    constructor(resizer) {
        this.overlay = resizer.overlay;
        this.img = resizer.img;
        this.options = resizer.options;
        this.requestUpdate = resizer.onUpdate;
    }

    onCreate = () => {
        this.boxes = [];

        // 8 handles for full control
        this.addBox('nwse-resize'); // 0: top left
        this.addBox('ns-resize');   // 1: top center
        this.addBox('nesw-resize'); // 2: top right
        this.addBox('ew-resize');   // 3: right center
        this.addBox('nwse-resize'); // 4: bottom right
        this.addBox('ns-resize');   // 5: bottom center
        this.addBox('nesw-resize'); // 6: bottom left
        this.addBox('ew-resize');   // 7: left center

        this.positionBoxes();
    };

    onDestroy = () => {
        this.setCursor('');
    };

    positionBoxes = () => {
        const handleXOffset = `${-parseFloat(this.options.handleStyles.width) / 2}px`;
        const handleYOffset = `${-parseFloat(this.options.handleStyles.height) / 2}px`;

        [
            { left: handleXOffset, top: handleYOffset },                  // top left
            { left: '50%', top: handleYOffset },                          // top center
            { right: handleXOffset, top: handleYOffset },                 // top right
            { right: handleXOffset, top: '50%' },                         // right center
            { right: handleXOffset, bottom: handleYOffset },              // bottom right
            { left: '50%', bottom: handleYOffset },                       // bottom center
            { left: handleXOffset, bottom: handleYOffset },               // bottom left
            { left: handleXOffset, top: '50%' },                          // left center
        ].forEach((pos, idx) => {
            Object.assign(this.boxes[idx].style, pos);
            if (pos.left === '50%' || pos.top === '50%') {
                this.boxes[idx].style.transform = 'translate(-50%, -50%)';
                if (pos.left === handleXOffset) this.boxes[idx].style.transform = 'translate(0, -50%)';
                if (pos.right === handleXOffset) this.boxes[idx].style.transform = 'translate(0, -50%)';
                if (pos.top === handleYOffset) this.boxes[idx].style.transform = 'translate(-50%, 0)';
                if (pos.bottom === handleYOffset) this.boxes[idx].style.transform = 'translate(-50%, 0)';
            }
        });
    };

    addBox = (cursor) => {
        const box = document.createElement('div');
        Object.assign(box.style, this.options.handleStyles);
        box.style.cursor = cursor;
        box.style.width = `${this.options.handleStyles.width}px`;
        box.style.height = `${this.options.handleStyles.height}px`;
        box.addEventListener('mousedown', this.handleMousedown, false);
        this.overlay.appendChild(box);
        this.boxes.push(box);
    };

    handleMousedown = (evt) => {
        this.dragBox = evt.target;
        this.dragStartX = evt.clientX;
        this.dragStartY = evt.clientY;
        this.preDragWidth = this.img.width || this.img.naturalWidth;
        this.preDragHeight = this.img.height || this.img.naturalHeight;
        this.setCursor(this.dragBox.style.cursor);
        document.addEventListener('mousemove', this.handleDrag, false);
        document.addEventListener('mouseup', this.handleMouseup, false);
    };

    handleMouseup = () => {
        this.setCursor('');
        document.removeEventListener('mousemove', this.handleDrag);
        document.removeEventListener('mouseup', this.handleMouseup);
    };

    handleDrag = (evt) => {
        if (!this.img) return;
        
        const deltaX = evt.clientX - this.dragStartX;
        const deltaY = evt.clientY - this.dragStartY;

        // Determine which box is being dragged
        const boxIdx = this.boxes.indexOf(this.dragBox);

        // Update width
        if ([0, 6, 7].includes(boxIdx)) { // Left side
            this.img.width = Math.round(this.preDragWidth - deltaX);
        } else if ([2, 3, 4].includes(boxIdx)) { // Right side
            this.img.width = Math.round(this.preDragWidth + deltaX);
        }

        // Update height
        if ([0, 1, 2].includes(boxIdx)) { // Top side
            this.img.height = Math.round(this.preDragHeight - deltaY);
        } else if ([4, 5, 6].includes(boxIdx)) { // Bottom side
            this.img.height = Math.round(this.preDragHeight + deltaY);
        }

        this.requestUpdate();
    };

    setCursor = (value) => {
        [document.body, this.img].forEach((el) => {
            if (el) el.style.cursor = value;
        });
    };
}
